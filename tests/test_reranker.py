from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.query_rewrite import rewrite_query
from enterprise_agent_kb.reranker import rerank_candidates
from enterprise_agent_kb.retrieval_router import route_retrieval


WORKSPACE = Path("knowledge_base")


def test_reranker_keeps_document_high_for_standard_lookup() -> None:
    rewritten = rewrite_query("QC/T 1036—2016 的实施日期是什么？")
    routed = route_retrieval(WORKSPACE, rewritten, limit=12)
    reranked = rerank_candidates(WORKSPACE, rewritten, routed["hits"], limit=12)

    assert reranked
    assert reranked[0]["doc_id"] == "DOC-000007"
    assert "rerank" in reranked[0]
    assert "final_score" in reranked[0]["rerank"]


def test_reranker_exposes_explanations_for_definition_query() -> None:
    rewritten = rewrite_query("什么是V2G")
    routed = route_retrieval(WORKSPACE, rewritten, limit=12)
    reranked = rerank_candidates(WORKSPACE, rewritten, routed["hits"], limit=12)

    assert any(item["result_type"] in {"fact", "wiki"} and item["doc_id"] == "DOC-000006" for item in reranked[:6])
    assert all("rerank" in item for item in reranked[:6])
