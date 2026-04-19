from __future__ import annotations

import json
from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.query_api import build_query_context

WORKSPACE = Path("knowledge_base")


def _normalize(value: str) -> str:
    text = value.lower().replace("—", "-").replace("／", "/")
    return "".join(text.split())


def _assert_case(case: dict[str, str]) -> None:
    expected = _normalize(case["must_include"])
    if case.get("assert_mode") == "context_contains":
        context = build_query_context(WORKSPACE, case["query"], limit=8)
        blob = json.dumps(context, ensure_ascii=False)
    else:
        answer = answer_query(WORKSPACE, case["query"], limit=8)
        blob = "\n".join(
            [
                str(answer.get("direct_answer", "")),
                *[str(item) for item in answer.get("summary", [])],
                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],
                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],
                *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],
            ]
        )
    assert expected in _normalize(blob)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_1() -> None:
    case = '{"kind": "network_standard", "query": "ISO 15118 的标准号是什么？", "must_include": "ISO 15118", "source": "network", "assert_mode": "rich_answer", "source_url": "https://www.evb.com/iso-15118-the-complete-guide-to-ev-charging-communication-standards-2026-edition/"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_2() -> None:
    case = '{"kind": "page_coverage", "query": "第1页 https://www.hanspub.org/journal/sg htt...", "must_include": "https://www.hanspub.org/journal/sg htt...", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_3() -> None:
    case = '{"kind": "page_coverage", "query": "第2页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 2}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_4() -> None:
    case = '{"kind": "page_coverage", "query": "第3页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 3}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_5() -> None:
    case = '{"kind": "page_coverage", "query": "第4页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 4}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_6() -> None:
    case = '{"kind": "page_coverage", "query": "第5页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 5}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_7() -> None:
    case = '{"kind": "page_coverage", "query": "第6页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 6}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_8() -> None:
    case = '{"kind": "page_coverage", "query": "第7页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 7}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_9() -> None:
    case = '{"kind": "page_coverage", "query": "第8页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 8}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_10() -> None:
    case = '{"kind": "page_coverage", "query": "第9页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 9}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_11() -> None:
    case = '{"kind": "page_coverage", "query": "第10页 山博轩，杨郁", "must_include": "山博轩，杨郁", "source": "local", "assert_mode": "context_contains", "page_no": 10}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_12() -> None:
    case = '{"kind": "definition", "query": "在ISO 15118中，什么是V2G？", "must_include": "V2G", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_13() -> None:
    case = '{"kind": "standard", "query": "ISO 15118 的标准号和实施日期是什么？", "must_include": "ISO 15118", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_14() -> None:
    case = '{"kind": "standard", "query": "ISO 15118 对应的标准编号是什么？", "must_include": "ISO 15118", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_15() -> None:
    case = '{"kind": "standard", "query": "ISO 15118 的现行标准号是什么？", "must_include": "ISO 15118", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_16() -> None:
    case = '{"kind": "keyword_evidence", "query": "Smart Grid 智能电网, 2024, 14(2)...", "must_include": "Smart Grid 智能电网, 2024, 14(2)...", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_17() -> None:
    case = '{"kind": "keyword_evidence", "query": "https://www.hanspub.org/jour...", "must_include": "https://www.hanspub.org/jour...", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_18() -> None:
    case = '{"kind": "keyword_evidence", "query": "从试点到成熟应用: V2G 发展展望[J].", "must_include": "从试点到成熟应用: V2G 发展展望[J].", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_19() -> None:
    case = '{"kind": "keyword_evidence", "query": "智能电网, 2024, 14(2): 11-20.", "must_include": "智能电网, 2024, 14(2): 11-20.", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000006_golden_20() -> None:
    case = '{"kind": "keyword_evidence", "query": "DOI: 10.12677/sg.2024.142002", "must_include": "DOI: 10.12677/sg.2024.142002", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))
