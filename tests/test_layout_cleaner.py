from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.layout_cleaner import clean_doc_ir, load_doc_ir
from enterprise_agent_kb.parse import parse_document


def test_clean_doc_ir_splits_large_markdown_blocks() -> None:
    doc_ir = load_doc_ir(Path("knowledge_base/normalized/DOC-000007.doc_ir.json"))
    cleaned = clean_doc_ir(doc_ir)

    assert cleaned.block_count >= doc_ir.block_count
    page8 = next(page for page in cleaned.pages if page.page_no == 8)
    assert len(page8.blocks) >= 2
    assert any(block.type == "heading" for block in page8.blocks)
    assert any(block.type in {"paragraph", "table"} for block in page8.blocks)


def test_parse_document_writes_cleaned_doc_ir() -> None:
    parse_document(Path("knowledge_base"), "DOC-000007")
    path = Path("knowledge_base/normalized/DOC-000007.cleaned_doc_ir.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["doc_id"] == "DOC-000007"
    assert payload["block_count"] >= 24
