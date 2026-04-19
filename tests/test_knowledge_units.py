from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.knowledge_units import extract_knowledge_units


def test_extract_knowledge_units_from_cleaned_doc_ir() -> None:
    bundle = extract_knowledge_units(Path("knowledge_base/normalized/DOC-000007.cleaned_doc_ir.json"))

    assert bundle.doc_id == "DOC-000007"
    assert bundle.unit_count > 0
    assert any(unit.type == "definition" for unit in bundle.units)
    assert any(unit.type == "requirement" for unit in bundle.units)
    assert any(unit.type == "table_requirement" for unit in bundle.units)
    assert any(unit.type == "procedure" for unit in bundle.units)
    assert not any(unit.type == "procedure" and unit.title == "前言" for unit in bundle.units)
    structured_requirements = [unit for unit in bundle.units if unit.type == "requirement" and unit.threshold]
    assert structured_requirements
    structured_tables = [unit for unit in bundle.units if unit.type == "table_requirement" and unit.headers]
    assert structured_tables
    assert any(unit.type == "table_requirement" and unit.table_no for unit in bundle.units)
