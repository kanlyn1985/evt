from __future__ import annotations

import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .query_rewrite import RewrittenQuery


def rerank_candidates(
    workspace_root: Path,
    rewritten: RewrittenQuery,
    candidates: list[dict[str, object]],
    limit: int = 20,
    connection=None,
) -> list[dict[str, object]]:
    own_connection = connection is None
    paths = AppPaths.from_root(workspace_root)
    if own_connection:
        connection = connect(paths.db_file)

    try:
        reranked: list[dict[str, object]] = []
        for candidate in candidates:
            rescored = dict(candidate)
            rescored["rerank"] = _score_candidate(connection, rewritten, candidate)
            rescored["score"] = rescored["rerank"]["final_score"]
            reranked.append(rescored)
        reranked.sort(key=lambda item: float(item["score"] or 0), reverse=True)
        return reranked[:limit]
    finally:
        if own_connection:
            connection.close()


def _score_candidate(connection, rewritten: RewrittenQuery, candidate: dict[str, object]) -> dict[str, object]:
    base_score = float(candidate.get("score") or 0.0)
    snippet = str(candidate.get("snippet", ""))
    result_type = str(candidate.get("result_type", ""))
    doc_id = str(candidate.get("doc_id", "") or "")

    lexical_score = _lexical_score(rewritten, snippet)
    exact_match_bonus = _exact_match_bonus(rewritten, snippet)
    standard_match_bonus = _standard_match_bonus(rewritten, snippet)
    term_match_bonus = _term_match_bonus(rewritten, snippet)
    type_bonus = _type_bonus(rewritten.query_type, result_type)
    title_bonus = _document_title_bonus(connection, doc_id, rewritten)
    quality_bonus, risk_penalty = _quality_adjustment(connection, doc_id)

    final_score = round(
        base_score
        + lexical_score
        + exact_match_bonus
        + standard_match_bonus
        + term_match_bonus
        + type_bonus
        + title_bonus
        + quality_bonus
        - risk_penalty,
        6,
    )
    return {
        "base_score": round(base_score, 6),
        "lexical_score": round(lexical_score, 6),
        "exact_match_bonus": round(exact_match_bonus, 6),
        "standard_match_bonus": round(standard_match_bonus, 6),
        "term_match_bonus": round(term_match_bonus, 6),
        "query_type_alignment_bonus": round(type_bonus, 6),
        "document_title_bonus": round(title_bonus, 6),
        "quality_bonus": round(quality_bonus, 6),
        "risk_penalty": round(risk_penalty, 6),
        "final_score": final_score,
    }


def _lexical_score(rewritten: RewrittenQuery, snippet: str) -> float:
    haystack = _norm(snippet)
    score = 0.0
    for term in [*rewritten.must_terms, *rewritten.should_terms]:
        normalized = _norm(term)
        if normalized and normalized in haystack:
            score += 0.08 if term in rewritten.must_terms else 0.04
    return score


def _exact_match_bonus(rewritten: RewrittenQuery, snippet: str) -> float:
    haystack = _norm(snippet)
    if rewritten.normalized_query and _norm(rewritten.normalized_query) in haystack:
        return 0.18
    return 0.0


def _standard_match_bonus(rewritten: RewrittenQuery, snippet: str) -> float:
    if rewritten.query_type not in {"standard_lookup", "lifecycle_lookup"}:
        return 0.0
    haystack = _norm(snippet)
    if any(_norm(term) in haystack for term in rewritten.must_terms):
        return 0.22
    return 0.0


def _term_match_bonus(rewritten: RewrittenQuery, snippet: str) -> float:
    if rewritten.query_type != "definition":
        return 0.0
    haystack = _norm(snippet)
    if rewritten.normalized_query and _norm(rewritten.normalized_query) in haystack:
        return 0.2
    return 0.0


def _type_bonus(query_type: str, result_type: str) -> float:
    matrix = {
        "definition": {"fact": 0.24, "wiki": 0.16, "evidence": 0.08, "document": 0.03},
        "standard_lookup": {"document": 0.24, "fact": 0.2, "wiki": 0.16, "evidence": 0.06},
        "lifecycle_lookup": {"document": 0.24, "fact": 0.2, "wiki": 0.14, "evidence": 0.06},
        "timing_lookup": {"fact": 0.26, "evidence": 0.2, "document": 0.06, "wiki": 0.04},
        "parameter_lookup": {"fact": 0.28, "evidence": 0.18, "wiki": 0.06, "document": -0.08},
        "section_lookup": {"fact": 0.22, "evidence": 0.16, "document": 0.14, "wiki": 0.04},
        "scope": {"evidence": 0.18, "fact": 0.12, "document": 0.1, "wiki": 0.05},
        "constraint": {"fact": 0.16, "evidence": 0.14, "document": 0.08, "wiki": 0.04},
        "general_search": {"evidence": 0.14, "fact": 0.1, "wiki": 0.08, "document": 0.05},
    }
    return matrix.get(query_type, {}).get(result_type, 0.0)


def _document_title_bonus(connection, doc_id: str, rewritten: RewrittenQuery) -> float:
    if not doc_id:
        return 0.0
    row = connection.execute(
        """
        SELECT source_filename
        FROM documents
        WHERE doc_id = ?
        """,
        (doc_id,),
    ).fetchone()
    if row is None:
        return 0.0
    filename = _norm(str(row["source_filename"]))
    if rewritten.normalized_query and _norm(rewritten.normalized_query) in filename:
        return 0.12
    if any(_norm(term) in filename for term in rewritten.must_terms):
        return 0.08
    return 0.0


def _quality_adjustment(connection, doc_id: str) -> tuple[float, float]:
    if not doc_id:
        return (0.0, 0.0)
    row = connection.execute(
        """
        SELECT overall_score, high_risk_page_count, blocked_count
        FROM quality_reports
        WHERE doc_id = ?
        """,
        (doc_id,),
    ).fetchone()
    if row is None:
        return (0.0, 0.0)
    quality_bonus = min(float(row["overall_score"] or 0.0) * 0.05, 0.05)
    risk_penalty = min(float(row["high_risk_page_count"] or 0.0) * 0.01 + float(row["blocked_count"] or 0.0) * 0.05, 0.2)
    return (quality_bonus, risk_penalty)


def _norm(value: str) -> str:
    text = value.lower().replace("—", "-").replace("_", "").replace("/", "")
    text = re.sub(r"\s+", "", text)
    return text
