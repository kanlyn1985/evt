from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .query_rewrite import rewrite_query
from .reranker import rerank_candidates
from .retrieval_router import route_retrieval


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def build_query_context(
    workspace_root: Path,
    query: str,
    limit: int = 8,
    preferred_doc_id: str | None = None,
) -> dict[str, object]:
    query = query.strip()
    rewritten = rewrite_query(query)
    if not query:
        return {
            "query": query,
            "rewrite": rewritten.to_dict(),
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
        }

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)

    try:
        routed = route_retrieval(paths.root, rewritten, limit=max(limit * 3, 20), connection=connection)
        reranked_hits = rerank_candidates(paths.root, rewritten, routed["hits"], limit=max(limit * 3, 20), connection=connection)
        hits = [hit for hit in reranked_hits if hit["result_type"] != "document"]
        if preferred_doc_id:
            preferred_doc_id = preferred_doc_id.strip()
            filtered_hits = [hit for hit in hits if hit.get("doc_id") == preferred_doc_id]
            if filtered_hits:
                hits = filtered_hits
        hits = _filter_hits_for_exact_terms(rewritten, hits)
        hits = _inject_exact_standard_hits(connection, query, hits, max(limit * 3, 20))
        hits = _inject_direct_wiki_hits(connection, rewritten, hits, max(limit * 3, 20))
        hits.sort(key=lambda item: float(item["score"] or 0), reverse=True)
        hits = hits[:limit]
        doc_ids = sorted({
            *(hit["doc_id"] for hit in hits if hit.get("doc_id")),
            *(hit["doc_id"] for hit in reranked_hits if hit.get("result_type") == "document" and hit.get("doc_id")),
            *([preferred_doc_id] if preferred_doc_id else []),
        })
        evidence_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "evidence"]
        fact_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "fact"]
        wiki_page_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "wiki"]

        evidence_items: list[dict[str, object]] = []
        entity_ids: set[str] = set()

        if evidence_ids:
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = connection.execute(
                f"""
                SELECT evidence_id, doc_id, page_no, confidence, risk_level, normalized_text
                FROM evidence
                WHERE evidence_id IN ({placeholders})
                ORDER BY confidence DESC, page_no ASC
                """,
                evidence_ids,
            ).fetchall()
            evidence_items = [dict(row) for row in rows]

        fact_items: list[dict[str, object]] = []
        if fact_ids:
            placeholders = ",".join("?" for _ in fact_ids)
            rows = connection.execute(
                f"""
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE fact_id IN ({placeholders})
                ORDER BY confidence DESC, fact_id ASC
                """,
                fact_ids,
            ).fetchall()
            for row in rows:
                item = dict(row)
                item["object_value"] = _safe_json(item["object_value"])
                item["qualifiers_json"] = _safe_json(item["qualifiers_json"])
                fact_items.append(item)
                if item.get("subject_entity_id"):
                    entity_ids.add(item["subject_entity_id"])
                if item.get("object_entity_id"):
                    entity_ids.add(item["object_entity_id"])

        fact_items = _augment_standard_facts(connection, query, fact_items)
        for item in fact_items:
            if item.get("subject_entity_id"):
                entity_ids.add(item["subject_entity_id"])
            if item.get("object_entity_id"):
                entity_ids.add(item["object_entity_id"])

        wiki_items: list[dict[str, object]] = []
        if wiki_page_ids:
            placeholders = ",".join("?" for _ in wiki_page_ids)
            rows = connection.execute(
                f"""
                SELECT page_id, page_type, title, slug, entity_id, trust_status, file_path, source_fact_ids_json
                FROM wiki_pages
                WHERE page_id IN ({placeholders})
                ORDER BY trust_status DESC, title ASC
                """,
                wiki_page_ids,
            ).fetchall()
            wiki_items = [dict(row) for row in rows]
            for item in wiki_items:
                if item.get("entity_id"):
                    entity_ids.add(item["entity_id"])
        wiki_items = _augment_query_wiki_items(connection, rewritten, wiki_items, doc_ids, limit)
        for item in wiki_items:
            if item.get("entity_id"):
                entity_ids.add(item["entity_id"])

        topic_objects = _resolve_topic_objects(rewritten, wiki_items)

        fact_items = _augment_facts_from_wiki(connection, fact_items, wiki_items, doc_ids)
        for item in fact_items:
            if item.get("subject_entity_id"):
                entity_ids.add(item["subject_entity_id"])
            if item.get("object_entity_id"):
                entity_ids.add(item["object_entity_id"])

        entity_items: list[dict[str, object]] = []
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            rows = connection.execute(
                f"""
                SELECT entity_id, canonical_name, entity_type, description, source_confidence
                FROM entities
                WHERE entity_id IN ({placeholders})
                ORDER BY entity_type, canonical_name
                """,
                list(entity_ids),
            ).fetchall()
            entity_items = [dict(row) for row in rows]

        edge_items: list[dict[str, object]] = []
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            rows = connection.execute(
                f"""
                SELECT edge_id, src_entity_id, relation, dst_entity_id, version_scope, confidence
                FROM graph_edges
                WHERE src_entity_id IN ({placeholders}) OR dst_entity_id IN ({placeholders})
                ORDER BY confidence DESC, edge_id ASC
                LIMIT ?
                """,
                [*entity_ids, *entity_ids, limit * 3],
            ).fetchall()
            edge_items = [dict(row) for row in rows]

        knowledge_subgraph = {
            "seed_wiki_page_ids": [item["page_id"] for item in wiki_items[:8]],
            "seed_entity_ids": sorted(entity_ids)[:20],
            "seed_fact_ids": [item["fact_id"] for item in fact_items[:80] if item.get("fact_id")],
            "seed_edge_ids": [item["edge_id"] for item in edge_items[:80] if item.get("edge_id")],
            "wiki_page_types": sorted({
                str(item.get("page_type") or "").strip()
                for item in wiki_items
                if str(item.get("page_type") or "").strip()
            }),
            "topic_object_ids": [item["page_id"] for item in topic_objects[:8] if item.get("page_id")],
            "fact_count": len(fact_items),
            "edge_count": len(edge_items),
            "wiki_count": len(wiki_items),
            "topic_count": len(topic_objects),
        }

        document_items: list[dict[str, object]] = []
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            rows = connection.execute(
                f"""
                SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
                FROM documents
                WHERE doc_id IN ({placeholders})
                ORDER BY doc_id
                """,
                doc_ids,
            ).fetchall()
            document_items = [dict(row) for row in rows]

        return {
            "query": query,
            "rewrite": rewritten.to_dict(),
            "preferred_doc_id": preferred_doc_id,
            "retrieval_plan": {
                "query_type": routed["query_type"],
                "channels": routed["channels"],
            },
            "rerank_explanations": [
                {
                    "result_type": hit["result_type"],
                    "result_id": hit["result_id"],
                    "doc_id": hit.get("doc_id"),
                    "rerank": hit.get("rerank", {}),
                }
                for hit in hits[: min(8, len(hits))]
            ],
            "hit_count": len(hits),
            "documents": document_items,
            "hits": hits,
            "evidence": evidence_items,
            "facts": fact_items,
            "entities": entity_items,
            "graph_edges": edge_items,
            "wiki_pages": wiki_items,
            "topic_objects": topic_objects,
            "knowledge_subgraph": knowledge_subgraph,
        }
    finally:
        connection.close()


def _inject_exact_standard_hits(connection, query: str, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    standard = _extract_standard_from_query(query)
    if not standard:
        return hits

    normalized = _normalize_standard_code(standard)
    rows = connection.execute(
        """
        SELECT fact_id, source_doc_id, object_value, confidence
        FROM facts
        WHERE fact_type = 'document_standard'
        """
    ).fetchall()

    exact_hits: list[dict[str, object]] = []
    for row in rows:
        payload = _safe_json(row["object_value"])
        if isinstance(payload, dict):
            value = str(payload.get("value", ""))
            if _normalize_standard_code(value) == normalized:
                exact_hits.append(
                    {
                        "result_type": "fact",
                        "result_id": row["fact_id"],
                        "doc_id": row["source_doc_id"],
                        "page_no": 1,
                        "score": max(0.99, float(row["confidence"] or 0)),
                        "snippet": f"standard_code {row['object_value']}",
                    }
                )

    merged: dict[tuple[str, str], dict[str, object]] = {(hit["result_type"], hit["result_id"]): hit for hit in hits}
    for hit in exact_hits:
        merged[(hit["result_type"], hit["result_id"])] = hit

    merged_hits = list(merged.values())
    merged_hits.sort(key=lambda item: float(item["score"] or 0), reverse=True)
    return merged_hits[: max(limit, len(exact_hits))]


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _extract_standard_from_query(query: str) -> str | None:
    match = re.search(r"(?:GB/T|GBT|GB|ISO|IEC)\s*[\d.]+(?:[-—]\d{2,4})?", query, re.I)
    return match.group(0) if match else None


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _augment_standard_facts(connection, query: str, fact_items: list[dict[str, object]]) -> list[dict[str, object]]:
    standard = _extract_standard_from_query(query)
    if not standard:
        return fact_items

    normalized = _normalize_standard_code(standard)
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE fact_type IN ('document_standard', 'document_lifecycle', 'document_versioning')
        ORDER BY fact_id
        """
    ).fetchall()

    matched_doc_ids: set[str] = set()
    existing_ids = {item["fact_id"] for item in fact_items}
    augmented = list(fact_items)

    for row in rows:
        if row["fact_type"] != "document_standard":
            continue
        payload = _safe_json(row["object_value"])
        if not isinstance(payload, dict):
            continue
        value = _normalize_standard_code(str(payload.get("value", "")))
        if value == normalized:
            matched_doc_ids.add(row["source_doc_id"])
            if row["fact_id"] not in existing_ids:
                augmented.append(_row_to_fact(row))
                existing_ids.add(row["fact_id"])

    if not matched_doc_ids:
        return augmented

    for row in rows:
        if row["source_doc_id"] not in matched_doc_ids:
            continue
        if row["fact_type"] not in {"document_lifecycle", "document_versioning"}:
            continue
        if row["fact_id"] in existing_ids:
            continue
        augmented.append(_row_to_fact(row))
        existing_ids.add(row["fact_id"])

    return augmented


def _row_to_fact(row) -> dict[str, object]:
    return {
        "fact_id": row["fact_id"],
        "fact_type": row["fact_type"],
        "predicate": row["predicate"],
        "object_value": _safe_json(row["object_value"]),
        "confidence": row["confidence"],
        "source_doc_id": row["source_doc_id"],
        "subject_entity_id": row["subject_entity_id"],
        "object_entity_id": row["object_entity_id"],
        "qualifiers_json": _safe_json(row["qualifiers_json"]),
    }


def _filter_hits_for_exact_terms(rewritten, hits: list[dict[str, object]]) -> list[dict[str, object]]:
    exact_terms = [term for term in rewritten.must_terms if re.fullmatch(r"[A-Z][A-Z0-9/-]{2,}", str(term or ""))]
    if not exact_terms:
        return hits
    if rewritten.query_type not in {"definition", "comparison", "general_search"}:
        return hits

    filtered = [hit for hit in hits if _hit_matches_exact_terms(hit, exact_terms)]
    return filtered or hits


def _hit_matches_exact_terms(hit: dict[str, object], exact_terms: list[str]) -> bool:
    blob = json.dumps(hit, ensure_ascii=False).upper()
    return any(term.upper() in blob for term in exact_terms)


def _inject_direct_wiki_hits(connection, rewritten, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type not in {"definition", "parameter_lookup", "timing_lookup", "comparison", "constraint"}:
        return hits

    search_terms = [
        rewritten.normalized_query,
        *rewritten.must_terms,
        *rewritten.aliases,
        *rewritten.should_terms,
    ]
    search_terms = [str(term).strip() for term in search_terms if str(term).strip()]

    wiki_hits: list[dict[str, object]] = []
    for term in search_terms[:10]:
        rows = connection.execute(
            """
            SELECT page_id, page_type, title, slug, json_extract(source_doc_ids_json, '$[0]') AS doc_id
            FROM wiki_pages
            WHERE title LIKE ? OR slug LIKE ?
            LIMIT ?
            """,
            (f"%{term}%", f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            bonus = 0.88
            if rewritten.query_type == "timing_lookup" and row["page_type"] == "process":
                bonus = 1.08
            elif rewritten.query_type == "parameter_lookup" and row["page_type"] == "parameter_group":
                bonus = 1.08
            elif rewritten.query_type == "definition" and row["page_type"] in {"term", "concept", "document"}:
                bonus = 1.02
            elif rewritten.query_type == "comparison" and row["page_type"] in {"term", "concept"}:
                bonus = 1.0
            elif rewritten.query_type == "comparison" and row["page_type"] == "comparison":
                bonus = 1.08
            elif rewritten.query_type == "constraint" and row["page_type"] == "constraint":
                bonus = 1.08
            elif rewritten.query_type == "constraint" and row["page_type"] in {"term", "process", "parameter_group"}:
                bonus = 0.96
            title = str(row["title"] or "").strip()
            if rewritten.query_type == "constraint":
                target_terms = _query_topic_terms(rewritten)
                if any(term and title == term for term in target_terms):
                    bonus += 0.4
                elif any(term and term in title for term in target_terms):
                    bonus += 0.2
            wiki_hits.append(
                {
                    "result_type": "wiki",
                    "result_id": row["page_id"],
                    "doc_id": row["doc_id"],
                    "page_no": 1,
                    "score": bonus,
                    "snippet": f"{row['title']} {row['slug']}",
                }
            )

    merged: dict[tuple[str, str], dict[str, object]] = {(hit["result_type"], hit["result_id"]): hit for hit in hits}
    for hit in wiki_hits:
        key = (hit["result_type"], hit["result_id"])
        existing = merged.get(key)
        if existing is None or float(hit["score"]) > float(existing.get("score") or 0):
            merged[key] = hit
    merged_hits = list(merged.values())
    merged_hits.sort(key=lambda item: float(item["score"] or 0), reverse=True)
    return merged_hits[:limit]


def _augment_query_wiki_items(connection, rewritten, wiki_items: list[dict[str, object]], doc_ids: list[str], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type not in {"definition", "parameter_lookup", "timing_lookup", "comparison", "constraint"}:
        return wiki_items

    search_terms = [
        rewritten.normalized_query,
        *rewritten.must_terms,
        *rewritten.aliases,
        *rewritten.should_terms,
    ]
    search_terms = [str(term).strip() for term in search_terms if str(term).strip()]

    allowed_doc_ids = set(doc_ids)
    existing_ids = {item["page_id"] for item in wiki_items}
    extra_items: list[dict[str, object]] = []
    for term in search_terms[:10]:
        rows = connection.execute(
            """
            SELECT page_id, page_type, title, slug, entity_id, trust_status, file_path, source_fact_ids_json,
                   json_extract(source_doc_ids_json, '$[0]') AS doc_id
            FROM wiki_pages
            WHERE (title LIKE ? OR slug LIKE ?)
            LIMIT ?
            """,
            (f"%{term}%", f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            if row["page_id"] in existing_ids:
                continue
            if allowed_doc_ids and row["doc_id"] not in allowed_doc_ids:
                continue
            payload = dict(row)
            payload.pop("doc_id", None)
            extra_items.append(payload)
            existing_ids.add(row["page_id"])
    if rewritten.query_type == "constraint":
        topic_terms = _query_topic_terms(rewritten)
        extra_items.sort(
            key=lambda item: (
                0 if any(term and str(item.get("title") or "") == term for term in topic_terms) else
                1 if any(term and term in str(item.get("title") or "") for term in topic_terms) else
                2,
                str(item.get("title") or ""),
            )
        )
    return wiki_items + extra_items


def _augment_facts_from_wiki(connection, fact_items: list[dict[str, object]], wiki_items: list[dict[str, object]], doc_ids: list[str]) -> list[dict[str, object]]:
    allowed_doc_ids = set(doc_ids)
    existing_ids = {item["fact_id"] for item in fact_items}
    extra_fact_ids: list[str] = []
    for item in wiki_items:
        source_fact_ids = _safe_json(item.get("source_fact_ids_json"))
        if isinstance(source_fact_ids, list):
            for fact_id in source_fact_ids:
                value = str(fact_id).strip()
                if value and value not in existing_ids and value not in extra_fact_ids:
                    extra_fact_ids.append(value)
    if not extra_fact_ids:
        return fact_items

    placeholders = ",".join("?" for _ in extra_fact_ids)
    rows = connection.execute(
        f"""
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE fact_id IN ({placeholders})
        ORDER BY confidence DESC, fact_id ASC
        """,
        extra_fact_ids,
    ).fetchall()
    augmented = list(fact_items)
    for row in rows:
        if allowed_doc_ids and row["source_doc_id"] not in allowed_doc_ids:
            continue
        item = _row_to_fact(row)
        item["_source_from_wiki"] = True
        if item["fact_id"] not in existing_ids:
            augmented.append(item)
            existing_ids.add(item["fact_id"])
    return augmented


def _query_topic_terms(rewritten) -> list[str]:
    values = [
        str(getattr(rewritten, "target_topic", "") or "").strip(),
        str(getattr(rewritten, "normalized_query", "") or "").strip(),
        *[str(item).strip() for item in getattr(rewritten, "must_terms", [])],
        *[str(item).strip() for item in getattr(rewritten, "aliases", [])],
    ]
    terms: list[str] = []
    for value in values:
        if not value:
            continue
        cleaned = re.sub(r"(有什么要求|要求是什么|应满足什么|应符合什么)$", "", value).strip()
        cleaned = cleaned.replace("的要求", "").replace("功能要求", "").replace("功能", "").strip()
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms[:10]


def _resolve_topic_objects(rewritten, wiki_items: list[dict[str, object]]) -> list[dict[str, object]]:
    topic_terms = _query_topic_terms(rewritten)
    if not topic_terms:
        return []

    scored: list[tuple[int, dict[str, object]]] = []
    for item in wiki_items:
        title = str(item.get("title") or "").strip()
        page_type = str(item.get("page_type") or "").strip()
        if not title:
            continue
        score = 0
        if any(term and title == term for term in topic_terms):
            score += 4
        if any(term and term in title for term in topic_terms):
            score += 2
        if rewritten.query_type == "constraint" and page_type == "constraint":
            score += 2
        elif rewritten.query_type == "comparison" and page_type == "comparison":
            score += 2
        elif rewritten.query_type == "timing_lookup" and page_type == "process":
            score += 2
        elif rewritten.query_type == "parameter_lookup" and page_type == "parameter_group":
            score += 2
        elif rewritten.query_type == "definition" and page_type in {"term", "concept"}:
            score += 2
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("title") or "")))
    topic_objects: list[dict[str, object]] = []
    seen: set[str] = set()
    for _, item in scored:
        page_id = str(item.get("page_id") or "")
        if page_id and page_id not in seen:
            seen.add(page_id)
            topic_objects.append(item)
    return topic_objects[:8]
