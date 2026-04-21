from __future__ import annotations

from enterprise_agent_kb.query_rewrite import rewrite_query


def test_rewrite_definition_query() -> None:
    rewritten = rewrite_query("V2G是怎么定义的")
    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "V2G"
    assert "V2G" in rewritten.must_terms


def test_rewrite_standard_lifecycle_query() -> None:
    rewritten = rewrite_query("QC/T 1036—2016 的实施日期是什么？")
    assert rewritten.query_type == "lifecycle_lookup"
    assert "QC/T1036—2016" in rewritten.must_terms


def test_rewrite_scope_query() -> None:
    rewritten = rewrite_query("本标准适用于什么范围？")
    assert rewritten.query_type == "scope"


def test_rewrite_constraint_query() -> None:
    rewritten = rewrite_query("逆变器必须满足哪些要求？")
    assert rewritten.query_type == "constraint"


def test_rewrite_parameter_query() -> None:
    rewritten = rewrite_query("CC阻值有哪些")
    assert rewritten.query_type == "parameter_lookup"
    assert "CC" in rewritten.must_terms
