from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.doc_ir import build_doc_ir
from enterprise_agent_kb.parse import parse_document


def test_build_doc_ir_maps_markdown_blocks() -> None:
    parsed_pages = [
        {
            "page_no": 1,
            "width": 100.0,
            "height": 200.0,
            "parser_confidence": 0.9,
            "ocr_confidence": 0.8,
            "blocks": [
                {"reading_order": 1, "block_type": "ocr_markdown", "text": "## 1 范围", "bbox": None},
                {"reading_order": 2, "block_type": "ocr_markdown", "text": "<table><tr><td>A</td></tr></table>", "bbox": None},
            ],
        }
    ]

    doc_ir = build_doc_ir(
        doc_id="DOC-TEST",
        parser_engine="paddlevl",
        source_type="pdf",
        parsed_pages=parsed_pages,
    )

    assert doc_ir.page_count == 1
    assert doc_ir.block_count == 2
    assert doc_ir.pages[0].blocks[0].type == "heading"
    assert doc_ir.pages[0].blocks[1].type == "table"
    assert doc_ir.pages[0].blocks[1].needs_llm is True


def test_parse_document_writes_doc_ir() -> None:
    result = parse_document(Path("knowledge_base"), "DOC-000001")
    doc_ir_path = Path("knowledge_base/normalized/DOC-000001.doc_ir.json")
    assert doc_ir_path.exists()
    payload = json.loads(doc_ir_path.read_text(encoding="utf-8"))
    assert payload["doc_id"] == "DOC-000001"
    assert payload["page_count"] >= 1
    assert payload["block_count"] >= 1
    assert result.doc_id == "DOC-000001"
