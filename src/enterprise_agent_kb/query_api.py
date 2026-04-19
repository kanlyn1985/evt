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
        hits.sort(key=lambda item: float(item["score"] or 0), reverse=True)
        hits = hits[:limit]
        doc_ids = sorted({
            *(hit["doc_id"] for hit in hits if hit.get("doc_id")),
            *(hit["doc_id"] for hit in reranked_hits if hit.get("result_type") == "document" and hit.get("doc_id")),
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
                SELECT page_id, page_type, title, slug, entity_id, trust_status, file_path
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
