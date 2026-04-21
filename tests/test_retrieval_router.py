from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.query_rewrite import rewrite_query
from enterprise_agent_kb.retrieval_router import route_retrieval


WORKSPACE = Path("knowledge_base")


def test_router_prefers_document_channel_for_standard_lookup() -> None:
    rewritten = rewrite_query("QC/T 1036—2016 的实施日期是什么？")
    routed = route_retrieval(WORKSPACE, rewritten, limit=12)

    assert routed["query_type"] in {"lifecycle_lookup", "standard_lookup"}
    assert routed["channels"][0] == "document"
    assert any(
        hit["result_type"] == "document" and hit["doc_id"] == "DOC-000006"
        for hit in routed["hits"]
    )


def test_router_uses_fact_channel_for_definition() -> None:
    rewritten = rewrite_query("什么是V2G")
    routed = route_retrieval(WORKSPACE, rewritten, limit=12)

    assert routed["query_type"] in {"definition", "general_search"}
    assert "facts" in routed["channels"] or "evidence" in routed["channels"]
    assert any(hit["doc_id"] in {"DOC-000005", "DOC-000002"} for hit in routed["hits"])
