from __future__ import annotations

import json
from pathlib import Path

from .config import AppPaths
from .db import connect
from .query_rewrite import RewrittenQuery
from .retrieval import search_knowledge_base_expanded


CHANNEL_PRIORITY: dict[str, list[str]] = {
    "definition": ["facts", "wiki", "evidence", "document"],
    "standard_lookup": ["document", "facts", "wiki", "evidence"],
    "lifecycle_lookup": ["document", "facts", "wiki", "evidence"],
    "section_lookup": ["document", "facts", "evidence", "wiki"],
    "scope": ["document", "evidence", "facts", "wiki"],
    "constraint": ["facts", "evidence", "document", "wiki"],
    "comparison": ["facts", "document", "evidence", "wiki"],
    "general_search": ["evidence", "facts", "wiki", "document"],
    "no_answer_candidate": ["document", "facts"],
}

CHANNEL_BOOST = {
    "facts": 1.0,
    "evidence": 0.96,
    "wiki": 0.98,
    "document": 2.2,
}


def route_retrieval(
    workspace_root: Path,
    rewritten: RewrittenQuery,
    limit: int = 10,
    connection=None,
) -> dict[str, object]:
    own_connection = connection is None
    paths = AppPaths.from_root(workspace_root)
    if own_connection:
        connection = connect(paths.db_file)

    try:
        channels = CHANNEL_PRIORITY.get(rewritten.query_type, CHANNEL_PRIORITY["general_search"])
        limit_per_channel = max(limit * 2, 12)

        channel_hits: dict[str, list[dict[str, object]]] = {}
        for channel in channels:
            if channel == "document":
                hits = _document_hits(connection, rewritten, limit_per_channel)
            else:
                hits = _structured_hits(paths.root, rewritten, channel, limit_per_channel, connection)
            for item in hits:
                item["channel"] = channel
                item["score"] = round(float(item.get("score") or 0) * CHANNEL_BOOST.get(channel, 1.0), 6)
            channel_hits[channel] = hits

        merged = _merge_channel_hits(channel_hits)
        merged.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return {
            "query_type": rewritten.query_type,
            "channels": channels,
            "channel_hits": channel_hits,
            "hits": merged[:limit],
        }
    finally:
        if own_connection:
            connection.close()


def _structured_hits(
    workspace_root: Path,
    rewritten: RewrittenQuery,
    channel: str,
    limit: int,
    connection,
) -> list[dict[str, object]]:
    seeds = [rewritten.normalized_query, *rewritten.must_terms, *rewritten.should_terms]
    merged: dict[tuple[str, str], dict[str, object]] = {}
    allowed_type = {"facts": "fact", "evidence": "evidence", "wiki": "wiki"}[channel]

    for seed in seeds:
        if not seed:
            continue
        hits = search_knowledge_base_expanded(workspace_root, seed, limit=limit, connection=connection)
        for hit in hits:
            if hit["result_type"] != allowed_type:
                continue
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"] or 0) > float(existing["score"] or 0):
                merged[key] = dict(hit)

    if channel == "facts" and rewritten.query_type in {"constraint", "section_lookup"}:
        for hit in _direct_fact_hits(connection, rewritten, limit):
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"] or 0) > float(existing["score"] or 0):
                merged[key] = dict(hit)
    return list(merged.values())[:limit]


def _document_hits(connection, rewritten: RewrittenQuery, limit: int) -> list[dict[str, object]]:
    seeds = [rewritten.normalized_query, *rewritten.must_terms, *rewritten.should_terms]
    hits: list[dict[str, object]] = []
    seen: set[str] = set()

    rows = connection.execute(
        """
        SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
        FROM documents
        ORDER BY ingest_time DESC
        """
    ).fetchall()
    for row in rows:
        blob = _normalize_document_blob(json.dumps(dict(row), ensure_ascii=False))
        score = 0.0
        for term in seeds:
            normalized = _normalize_document_blob(str(term or ""))
            if not normalized:
                continue
            if normalized in blob:
                score += 1.0
        if score <= 0:
            continue
        doc_id = row["doc_id"]
        if doc_id in seen:
            continue
        seen.add(doc_id)
        hits.append(
            {
                "result_type": "document",
                "result_id": doc_id,
                "doc_id": doc_id,
                "page_no": 1,
                "score": round(score / max(len(seeds), 1), 6),
                "snippet": row["source_filename"],
            }
        )
        if len(hits) >= limit:
            break
    return hits


def _normalize_document_blob(value: str) -> str:
    text = value.lower()
    text = text.replace("—", "-").replace("_", "").replace("/", "").replace("\\", "")
    text = text.replace("gb t", "gbt").replace("qc t", "qct")
    return "".join(text.split())


def _merge_channel_hits(channel_hits: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for channel, hits in channel_hits.items():
        for hit in hits:
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"] or 0) > float(existing["score"] or 0):
                merged[key] = dict(hit)
                merged[key]["channels"] = [channel]
            elif channel not in existing.get("channels", []):
                existing["channels"].append(channel)
    return list(merged.values())


def _direct_fact_hits(connection, rewritten: RewrittenQuery, limit: int) -> list[dict[str, object]]:
    search_terms = [*rewritten.must_terms, *rewritten.should_terms, rewritten.normalized_query]
    search_terms = [term for term in search_terms if term]
    hits: list[dict[str, object]] = []
    seen: set[str] = set()

    for term in search_terms[:6]:
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('requirement', 'table_requirement', 'threshold')
              AND object_value LIKE ?
            ORDER BY confidence DESC, fact_id ASC
            LIMIT ?
            """,
            (f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            if row["fact_id"] in seen:
                continue
            seen.add(row["fact_id"])
            hits.append(
                {
                    "result_type": "fact",
                    "result_id": row["fact_id"],
                    "doc_id": row["source_doc_id"],
                    "page_no": row["page_no"],
                    "score": max(0.85, float(row["confidence"] or 0)),
                    "snippet": f"knowledge_unit_fact {row['object_value']}",
                }
            )
    return hits[:limit]
