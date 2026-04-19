from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.structure_recovery import recover_structure_from_doc_ir


def test_recover_structure_from_doc_ir_extracts_sections() -> None:
    structure = recover_structure_from_doc_ir(Path("knowledge_base/normalized/DOC-000007.doc_ir.json"))

    assert structure.doc_id == "DOC-000007"
    assert structure.sections
    assert any("汽车电源逆变器" in item.title for item in structure.sections)
    assert any(item.section_number in {"4.2", "4.6.4", "5.10", "7"} for item in structure.sections)
