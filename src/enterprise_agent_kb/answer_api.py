from __future__ import annotations

import json
import re
from pathlib import Path

from .answer_policy import build_direct_answer as policy_build_direct_answer
from .answer_policy import build_summary_lines, select_answer_policy
from .confidence import compute_confidence_score
from .config import AppPaths
from .db import connect
from .query_api import build_query_context
from .query_rewrite import rewrite_query


def answer_query(
    workspace_root: Path,
    query: str,
    limit: int = 8,
) -> dict[str, object]:
    rewritten = rewrite_query(query)
    context = build_query_context(workspace_root, query, limit=limit)
    intent = _intent_from_query_type(rewritten.query_type)
    answer_mode = select_answer_policy(rewritten.query_type)
    exact_terms = _extract_exact_terms(query)
    if exact_terms and not _context_matches_exact_terms(context, exact_terms):
        context = {
            "query": query,
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
        }
    if rewritten.query_type == "comparison" and exact_terms and not _context_has_exact_definition_signal(context, exact_terms):
        context = {
            "query": query,
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
        }
    primary_doc_id = _choose_primary_doc_id(workspace_root, query, context, intent)

    if primary_doc_id:
        context = _restrict_context_to_doc(workspace_root, context, primary_doc_id)

    documents = context.get("documents", [])
    facts = _rank_facts(context.get("facts", []), intent, query=query)
    facts = _augment_facts(workspace_root, documents, facts, query, intent)
    evidence = _select_supporting_evidence(workspace_root, facts, query, intent)
    if not evidence:
        evidence = _rank_evidence(context.get("evidence", []), query, intent)[:5]
    graph_edges = _filter_graph_edges(context.get("graph_edges", []), facts)
    wiki_pages = _filter_wiki_pages(context.get("wiki_pages", []), facts, query, intent)

    fact_summaries = _summarize_facts(facts[:5], intent=intent)
    summary_lines = build_summary_lines(
        policy=answer_mode,
        documents=documents,
        facts=facts,
        evidence=evidence,
        fact_summaries=fact_summaries,
    )

    warnings: list[str] = []
    for doc in documents:
        if doc.get("quality_status") in {"review_required", "blocked"}:
            warnings.append(
                f"{doc['doc_id']} 质量状态为 {doc['quality_status']}，回答应回看原始证据。"
            )

    evidence_items = [
        {
            "evidence_id": item["evidence_id"],
            "doc_id": item["doc_id"],
            "page_no": item["page_no"],
            "confidence": item["confidence"],
            "snippet": _truncate(item["normalized_text"], 600),
        }
        for item in evidence[:5]
    ]

    fact_items = [
        {
            "fact_id": item["fact_id"],
            "fact_type": item["fact_type"],
            "predicate": item["predicate"],
            "object": item["object_value"],
            "confidence": item["confidence"],
            "doc_id": item["source_doc_id"],
        }
        for item in facts[:8]
    ]

    direct_answer = policy_build_direct_answer(
        policy=answer_mode,
        query=query,
        facts=fact_items,
        evidence=evidence_items,
        wiki_pages=wiki_pages,
        standard_normalizer=_normalize_standard_code,
        standard_extractor=_extract_standard_from_query,
        truncate_fn=_truncate,
    )
    confidence_score = compute_confidence_score(
        answer_mode=answer_mode,
        direct_answer=direct_answer,
        supporting_facts=fact_items[:3],
        supporting_evidence=evidence_items[:2],
        warnings=warnings,
    )

    return {
        "query": query,
        "rewrite": rewritten.to_dict(),
        "answer_mode": answer_mode,
        "confidence_score": confidence_score,
        "direct_answer": direct_answer,
        "summary": summary_lines,
        "supporting_facts": fact_items[:3],
        "supporting_evidence": evidence_items[:2],
        "related_graph_edges": graph_edges[:4],
        "related_wiki_pages": wiki_pages[:3],
        "warnings": warnings,
        "context": context,
    }


def _intent_from_query_type(query_type: str) -> str:
    if query_type in {"definition"}:
        return "definition"
    if query_type in {"standard_lookup", "lifecycle_lookup"}:
        return "standard"
    if query_type in {"comparison"}:
        return "general"
    return "general"


def _choose_primary_doc_id(workspace_root: Path, query: str, context: dict[str, object], intent: str) -> str | None:
    documents = context.get("documents", [])
    if not documents:
        return None

    if intent == "standard":
        normalized_query = _normalize_standard_code(_extract_standard_from_query(query))
        paths = AppPaths.from_root(workspace_root)
        connection = connect(paths.db_file)
        try:
            rows = connection.execute(
                """
                SELECT source_doc_id, object_value
                FROM facts
                WHERE fact_type = 'document_standard'
                """
            ).fetchall()
            for row in rows:
                payload = _safe_json(row["object_value"])
                if isinstance(payload, dict):
                    value = _normalize_standard_code(str(payload.get("value", "")))
                    if value and value == normalized_query:
                        return row["source_doc_id"]
            rows = connection.execute(
                """
                SELECT json_extract(source_doc_ids_json, '$[0]') AS doc_id, title
                FROM wiki_pages
                WHERE page_type = 'standard'
                """
            ).fetchall()
            for row in rows:
                if _normalize_standard_code(str(row["title"])) == normalized_query:
                    return row["doc_id"]
        finally:
            connection.close()

    normalized_phrase = _normalize_query_phrase(query)
    if normalized_phrase:
        best_doc_id = _choose_doc_by_phrase_match(workspace_root, normalized_phrase, intent)
        if best_doc_id:
            return best_doc_id

    return documents[0]["doc_id"]


def _restrict_context_to_doc(workspace_root: Path, context: dict[str, object], doc_id: str) -> dict[str, object]:
    filtered = dict(context)
    documents = [item for item in context.get("documents", []) if item.get("doc_id") == doc_id]
    if not documents:
        filtered["documents"] = [_load_document_record(workspace_root, doc_id)]
    else:
        filtered["documents"] = documents
    filtered["hits"] = [item for item in context.get("hits", []) if item.get("doc_id") == doc_id]
    filtered["evidence"] = [item for item in context.get("evidence", []) if item.get("doc_id") == doc_id]
    filtered["facts"] = [item for item in context.get("facts", []) if item.get("source_doc_id") == doc_id]
    filtered["wiki_pages"] = [
        item for item in context.get("wiki_pages", [])
        if item.get("page_id") in {hit["result_id"] for hit in filtered["hits"] if hit.get("result_type") == "wiki"}
        or item.get("entity_id") in {
            fact.get("subject_entity_id") for fact in filtered["facts"] if fact.get("subject_entity_id")
        } | {
            fact.get("object_entity_id") for fact in filtered["facts"] if fact.get("object_entity_id")
        }
    ]
    filtered["entities"] = [
        item for item in context.get("entities", [])
        if item.get("entity_id") in {
            fact.get("subject_entity_id") for fact in filtered["facts"] if fact.get("subject_entity_id")
        } | {
            fact.get("object_entity_id") for fact in filtered["facts"] if fact.get("object_entity_id")
        }
    ]
    filtered["graph_edges"] = [
        item for item in context.get("graph_edges", [])
        if item.get("version_scope") == doc_id
    ]
    filtered["hit_count"] = len(filtered["hits"])
    return filtered


def _load_document_record(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        row = connection.execute(
            """
            SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        return dict(row) if row else {"doc_id": doc_id}
    finally:
        connection.close()


def _detect_intent(query: str) -> str:
    if re.search(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)\b", query, re.I):
        return "standard"
    if re.search(r"(什么是|是什么|定义|怎么定义|如何定义|是怎么定义的|如何理解|怎么理解)", query):
        return "definition"
    return "general"


def _augment_facts(
    workspace_root: Path,
    documents: list[dict[str, object]],
    facts: list[dict[str, object]],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    if not documents:
        return facts

    doc_id = documents[0]["doc_id"]
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)

    try:
        extra: list[dict[str, object]] = []
        if intent == "standard":
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('document_standard', 'document_versioning', 'document_lifecycle')
                ORDER BY fact_id
                """,
                (doc_id,),
            ).fetchall()
            extra = [_row_to_fact(row) for row in rows]
        elif intent == "definition":
            normalized_query = _normalize_query_phrase(query)
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('term_definition', 'concept_definition', 'document_abstract')
                  AND object_value LIKE ?
                ORDER BY confidence DESC, fact_id ASC
                LIMIT 5
                """,
                (doc_id, f"%{normalized_query}%"),
            ).fetchall()
            extra = [_row_to_fact(row) for row in rows]
        else:
            normalized_query = _normalize_query_phrase(query)
            if re.search(r"表\s*\d+", query):
                rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type IN ('table_requirement', 'requirement', 'threshold')
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 20
                    """,
                    (doc_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type IN ('requirement', 'table_requirement', 'threshold')
                      AND object_value LIKE ?
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 12
                    """,
                    (doc_id, f"%{normalized_query}%"),
                ).fetchall()
            extra = [_row_to_fact(row) for row in rows]

        seen = {item["fact_id"] for item in facts}
        for item in extra:
            if item["fact_id"] not in seen:
                facts.append(item)
                seen.add(item["fact_id"])
        return _rank_facts(facts, intent, query=query)
    finally:
        connection.close()


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


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _normalize_query_phrase(query: str) -> str:
    text = query
    matched_pattern = False
    for pattern in (
        r"^\s*(.+?)\s*是怎么定义的\s*$",
        r"^\s*(.+?)\s*怎么定义\s*$",
        r"^\s*(.+?)\s*如何定义\s*$",
        r"^\s*(.+?)\s*是什么\s*$",
        r"^\s*(.+?)\s*要求是什么\s*$",
        r"^\s*(.+?)\s*有什么要求\s*$",
        r"^\s*(.+?)\s*有哪些字段\s*$",
        r"^\s*(.+?)\s*包括哪些字段\s*$",
        r"^\s*什么是\s*(.+?)\s*$",
        r"^\s*(.+?)\s*如何理解\s*$",
        r"^\s*(.+?)\s*怎么理解\s*$",
    ):
        match = re.match(pattern, text)
        if match:
            captured = next(group for group in match.groups() if group)
            text = captured
            matched_pattern = True
            break
    if not matched_pattern:
        text = re.sub(r"(什么是|是什么|是怎么定义的|怎么定义|如何定义|如何理解|定义|要求是什么|有什么要求|有哪些字段|包括哪些字段)", " ", text)
    text = text.replace("？", " ").replace("?", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_standard_from_query(query: str) -> str:
    match = re.search(r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[\d.]+(?:[—-]\d{2,4})?", query, re.I)
    return match.group(0) if match else query


def _extract_exact_terms(query: str) -> list[str]:
    terms = re.findall(r"[A-Z][A-Z0-9/-]{2,}", query)
    normalized: list[str] = []
    for term in terms:
        if term not in normalized and term not in {"GB", "GBT", "ISO", "IEC", "QC"}:
            normalized.append(term)
    return normalized


def _context_matches_exact_terms(context: dict[str, object], exact_terms: list[str]) -> bool:
    if not exact_terms:
        return True
    corpus_parts: list[str] = []
    for collection_name in ("hits", "evidence", "facts", "wiki_pages", "documents"):
        for item in context.get(collection_name, []):
            corpus_parts.append(json.dumps(item, ensure_ascii=False))
    corpus = "\n".join(corpus_parts).upper()
    return any(term.upper() in corpus for term in exact_terms)


def _context_has_exact_definition_signal(context: dict[str, object], exact_terms: list[str]) -> bool:
    if not exact_terms:
        return True
    corpus_parts: list[str] = []
    for collection_name in ("hits", "evidence", "facts", "wiki_pages"):
        for item in context.get(collection_name, []):
            corpus_parts.append(json.dumps(item, ensure_ascii=False))
    corpus = "\n".join(corpus_parts).upper()
    for term in exact_terms:
        target = term.upper()
        if target in corpus and any(token in corpus for token in ("TYPE", "V2X", "V2G", "V2V", "VEHICLE TO", "车辆", "电网", "负荷")):
            return True
    return False


def _rank_facts(facts: list[dict[str, object]], intent: str, query: str = "") -> list[dict[str, object]]:
    target_standard = _normalize_standard_code(_extract_standard_from_query(query)) if intent == "standard" else None
    def score(item: dict[str, object]) -> tuple[float, float]:
        fact_type = item.get("fact_type")
        confidence = float(item.get("confidence") or 0)
        bonus = 0.0
        if intent == "definition":
            if fact_type in {"term_definition", "concept_definition"}:
                bonus = 4.0
            elif fact_type == "document_abstract":
                bonus = 3.0
            elif fact_type == "section_heading":
                bonus = 1.5
        elif intent == "standard":
            if fact_type in {"document_standard", "document_versioning", "document_lifecycle"}:
                bonus = 3.0
            elif fact_type in {"term_definition", "concept_definition"}:
                bonus = 0.5
            if fact_type == "document_standard" and isinstance(item.get("object_value"), dict):
                value = _normalize_standard_code(str(item["object_value"].get("value", "")))
                if value and target_standard and value == target_standard:
                    bonus += 2.0
        else:
            if fact_type in {"term_definition", "concept_definition"}:
                bonus = 1.0
            elif fact_type == "requirement":
                bonus = 2.0
            elif fact_type == "threshold":
                bonus = 1.8
            elif fact_type == "table_requirement":
                bonus = 1.6
            if re.search(r"表\s*\d+", query) and fact_type == "table_requirement":
                bonus += 1.2
            if re.search(r"(字段|表头|参数)", query) and fact_type == "table_requirement":
                bonus += 0.8
        return (bonus + confidence, confidence)

    return sorted(facts, key=score, reverse=True)


def _select_supporting_evidence(
    workspace_root: Path,
    facts: list[dict[str, object]],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    fact_ids = [item["fact_id"] for item in facts[:6] if item.get("fact_id")]
    if not fact_ids:
        return []

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        placeholders = ",".join("?" for _ in fact_ids)
        rows = connection.execute(
            f"""
            SELECT DISTINCT e.evidence_id, e.doc_id, e.page_no, e.confidence, e.risk_level, e.normalized_text
            FROM fact_evidence_map m
            JOIN evidence e ON e.evidence_id = m.evidence_id
            WHERE m.fact_id IN ({placeholders})
            """,
            fact_ids,
        ).fetchall()
        evidence = [dict(row) for row in rows]
        return _rank_evidence(evidence, query, intent)
    finally:
        connection.close()


def _rank_evidence(evidence: list[dict[str, object]], query: str, intent: str) -> list[dict[str, object]]:
    def score(item: dict[str, object]) -> tuple[float, float]:
        text = item.get("normalized_text", "")
        confidence = float(item.get("confidence") or 0)
        bonus = 0.0
        if intent == "definition":
            if "##" in text and any(token in text for token in (" control pilot ", "控制导引电路", "定义", "术语")):
                bonus += 2.5
            if "##" in text:
                bonus += 0.5
        elif intent == "standard":
            if re.search(r"\d{4}-\d{2}-\d{2}\s*(发布|实施)", text):
                bonus += 1.5
            if re.search(r"\bGB/T\b", text):
                bonus += 1.0
        else:
            if "<table" in text.lower():
                bonus -= 1.2
            if "##" in text:
                bonus += 0.6
            if any(token in text for token in ("定义", "范围", "适用于")):
                bonus += 0.4
        if query and query.replace("？", "").replace("?", "")[:8] in text:
            bonus += 0.8
        return (bonus + confidence, confidence)

    return sorted(evidence, key=score, reverse=True)


def _filter_graph_edges(edges: list[dict[str, object]], facts: list[dict[str, object]]) -> list[dict[str, object]]:
    entity_ids: set[str] = set()
    for item in facts[:8]:
        if item.get("subject_entity_id"):
            entity_ids.add(item["subject_entity_id"])
        if item.get("object_entity_id"):
            entity_ids.add(item["object_entity_id"])

    filtered = [
        edge
        for edge in edges
        if edge.get("src_entity_id") in entity_ids or edge.get("dst_entity_id") in entity_ids
    ]
    return filtered or edges


def _filter_wiki_pages(
    wiki_pages: list[dict[str, object]],
    facts: list[dict[str, object]],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    if intent == "standard":
        target = _normalize_standard_code(_extract_standard_from_query(query))
        exact = [item for item in wiki_pages if _normalize_standard_code(str(item.get("title", ""))) == target]
        if exact:
            return exact + [item for item in wiki_pages if item not in exact]

    entity_ids = {
        item.get("subject_entity_id")
        for item in facts[:8]
        if item.get("subject_entity_id")
    } | {
        item.get("object_entity_id")
        for item in facts[:8]
        if item.get("object_entity_id")
    }
    filtered = [item for item in wiki_pages if item.get("entity_id") in entity_ids]
    return filtered or wiki_pages


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _summarize_facts(facts: list[dict[str, object]], intent: str = "general") -> list[str]:
    lines: list[str] = []
    for item in facts:
        payload = item.get("object_value")
        if item["fact_type"] == "document_standard" and isinstance(payload, dict):
            lines.append(f"标准号: {payload.get('value', '')}")
        elif item["fact_type"] == "document_versioning" and isinstance(payload, dict):
            lines.append(f"代替标准: {payload.get('value', '')}")
        elif item["fact_type"] == "document_lifecycle" and isinstance(payload, dict):
            label = "发布日期" if item["predicate"] == "publication_date" else "实施日期"
            lines.append(f"{label}: {payload.get('value', '')}")
        elif item["fact_type"] in {"term_definition", "concept_definition"} and isinstance(payload, dict):
            term = payload.get("term", "")
            definition = payload.get("definition", "")
            if term and definition:
                lines.append(f"{term}: {_truncate(str(definition), 120)}")
        elif item["fact_type"] == "document_abstract" and isinstance(payload, dict):
            value = payload.get("value", "")
            if value:
                lines.append(f"摘要: {_truncate(str(value), 120)}")
        elif item["fact_type"] == "section_heading" and isinstance(payload, dict):
            title = payload.get("title", "")
            if title:
                lines.append(f"相关章节: {title}")

    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    if intent == "definition":
        return deduped[:4]
    return deduped[:6]


def _choose_doc_by_phrase_match(workspace_root: Path, normalized_phrase: str, intent: str) -> str | None:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        scores: dict[str, float] = {}

        def bump(doc_id: str | None, score: float) -> None:
            if doc_id:
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        fact_rows = connection.execute(
            """
            SELECT source_doc_id, fact_type, object_value
            FROM facts
            WHERE fact_type IN (
                'term_definition',
                'concept_definition',
                'document_title',
                'document_standard',
                'requirement',
                'table_requirement',
                'threshold'
            )
            """
        ).fetchall()
        for row in fact_rows:
            payload = _safe_json(row["object_value"])
            text_parts: list[str] = []
            if isinstance(payload, dict):
                text_parts.extend(str(value) for value in payload.values())
            elif payload:
                text_parts.append(str(payload))
            haystack = " ".join(text_parts)
            if normalized_phrase and normalized_phrase in haystack:
                weight = 4.0 if row["fact_type"] in {"term_definition", "concept_definition"} else 2.5
                if row["fact_type"] == "requirement":
                    weight = 4.2
                elif row["fact_type"] == "threshold":
                    weight = 4.0
                elif row["fact_type"] == "table_requirement":
                    weight = 4.1
                if intent == "definition" and row["fact_type"] in {"term_definition", "concept_definition"}:
                    weight += 2.0
                bump(row["source_doc_id"], weight)

        wiki_rows = connection.execute(
            """
            SELECT json_extract(source_doc_ids_json, '$[0]') AS doc_id, title, slug, page_type
            FROM wiki_pages
            """
        ).fetchall()
        for row in wiki_rows:
            haystack = f"{row['title']} {row['slug']}"
            if normalized_phrase and normalized_phrase in haystack:
                weight = 3.0 if row["page_type"] == "term" else 1.5
                bump(row["doc_id"], weight)

        evidence_rows = connection.execute(
            """
            SELECT doc_id, normalized_text
            FROM evidence
            WHERE normalized_text LIKE ?
            LIMIT 20
            """,
            (f"%{normalized_phrase}%",),
        ).fetchall()
        for row in evidence_rows:
            bump(row["doc_id"], 1.0)

        if not scores:
            return None
        return max(scores.items(), key=lambda item: item[1])[0]
    finally:
        connection.close()
