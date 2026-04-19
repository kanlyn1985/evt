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
def test_doc_000009_golden_1() -> None:
    case = '{"kind": "network_standard", "query": "GB/T 18487. 的标准号是什么？", "must_include": "GB/T 18487.", "source": "network", "assert_mode": "rich_answer", "source_url": "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=AEF144D5381E9FDBD265AFA5A87595A3"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_2() -> None:
    case = '{"kind": "network_publication_date", "query": "GB/T 18487. 的发布日期是什么？", "must_include": "2024-12-31", "source": "network", "assert_mode": "rich_answer", "source_url": "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=AEF144D5381E9FDBD265AFA5A87595A3"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_3() -> None:
    case = '{"kind": "network_effective_date", "query": "GB/T 18487. 的实施日期是什么？", "must_include": "2024-12-31", "source": "network", "assert_mode": "rich_answer", "source_url": "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=AEF144D5381E9FDBD265AFA5A87595A3"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_4() -> None:
    case = '{"kind": "network_title", "query": "GB/T 18487. 的中文名称是什么？", "must_include": "电动汽车传导充电系统", "source": "network", "assert_mode": "rich_answer", "source_url": "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=AEF144D5381E9FDBD265AFA5A87595A3"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_5() -> None:
    case = '{"kind": "page_coverage", "query": "第1页 3的直流 充电系统 Electricvehicleconductivecha...", "must_include": "3的直流 充电系统 Electricvehicleconductivecha...", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_6() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487. 的标准号和实施日期是什么？", "must_include": "GB/T 18487.", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_7() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487. 对应的标准编号是什么？", "must_include": "GB/T 18487.", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_8() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487. 的现行标准号是什么？", "must_include": "GB/T 18487.", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_9() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 18487. 是哪一天发布的？", "must_include": "2024-12-31", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_10() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 18487. 从哪一天开始实施？", "must_include": "2024-12-31", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_11() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“范围”这一章节？", "must_include": "范围", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_12() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“在整个充电过程中,若车辆接口处于完全连接状态,车辆应支持辅源唤醒或充电机唤醒报文”这一章节？", "must_include": "在整个充电过程中,若车辆接口处于完全连接状态,车辆应支持辅源唤醒或充电机唤醒报文", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_13() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“当接触器K5、K6断开或车辆接口电压绝对值降至DC60V 以下时,车辆应控制闭合开”这一章节？", "must_include": "当接触器K5、K6断开或车辆接口电压绝对值降至DC60V 以下时,车辆应控制闭合开", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_14() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“若仅使用一个车辆插座进行充电,另一个车辆插座的B 级电压触头之间以及B 级电压触头”这一章节？", "must_include": "若仅使用一个车辆插座进行充电,另一个车辆插座的B 级电压触头之间以及B 级电压触头", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_15() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“在整个充电过程中,非车载充电机控制器应能监测接触器K1、K2、K3和K4的状态并控制其断”这一章节？", "must_include": "在整个充电过程中,非车载充电机控制器应能监测接触器K1、K2、K3和K4的状态并控制其断", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_16() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“充电机应检测直流充电回路DC+与PE 之间、DC-与PE 之间的绝缘电阻(取两者最小值为”这一章节？", "must_include": "充电机应检测直流充电回路DC+与PE 之间、DC-与PE 之间的绝缘电阻(取两者最小值为", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_17() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“在故障停机阶段,车辆不应进行接触器K5、K6的粘连检测。”这一章节？", "must_include": "在故障停机阶段,车辆不应进行接触器K5、K6的粘连检测。", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_18() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“供电模式阶段由充电机实施直流供电回路绝缘监测,应满足A.”这一章节？", "must_include": "供电模式阶段由充电机实施直流供电回路绝缘监测,应满足A.", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_19() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.中，是否包含“绝缘自检前,充电机在K1、K2闭合前先检测K1、K2外侧电压绝对值不应大于DC60V,确”这一章节？", "must_include": "绝缘自检前,充电机在K1、K2闭合前先检测K1、K2外侧电压绝对值不应大于DC60V,确", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_20() -> None:
    case = '{"kind": "title", "query": "GB/T 18487. 这份文档的标题是什么？", "must_include": "电动汽车传导充电系统", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))
