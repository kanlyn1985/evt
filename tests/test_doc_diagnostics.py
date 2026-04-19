from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.doc_diagnostics import build_document_diagnostics


WORKSPACE = Path("knowledge_base")


def test_doc7_diagnostics_exposes_core_metrics() -> None:
    diagnostics = build_document_diagnostics(WORKSPACE, "DOC-000007")

    assert diagnostics["doc_id"] == "DOC-000007"
    assert diagnostics["counts"]["page_count"] >= 20
    assert diagnostics["counts"]["evidence_count"] >= 10
    assert diagnostics["counts"]["fact_count"] >= 50
    assert diagnostics["coverage"]["answerability_score"] > 0
    assert "metadata_coverage" in diagnostics["coverage"]
    assert "warnings" in diagnostics
