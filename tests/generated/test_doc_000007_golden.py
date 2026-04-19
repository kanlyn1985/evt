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
def test_doc_000007_golden_1() -> None:
    case = '{"kind": "network_standard", "query": "QC/T 1036—2016 的标准号是什么？", "must_include": "QC/T 1036—2016", "source": "network", "assert_mode": "rich_answer", "source_url": "https://max.book118.com/html/2023/0809/6104213203005211.shtm"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_2() -> None:
    case = '{"kind": "network_publication_date", "query": "QC/T 1036—2016 的发布日期是什么？", "must_include": "2016-04-05", "source": "network", "assert_mode": "rich_answer", "source_url": "https://max.book118.com/html/2023/0809/6104213203005211.shtm"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_3() -> None:
    case = '{"kind": "network_effective_date", "query": "QC/T 1036—2016 的实施日期是什么？", "must_include": "2016-09-01", "source": "network", "assert_mode": "rich_answer", "source_url": "https://max.book118.com/html/2023/0809/6104213203005211.shtm"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_4() -> None:
    case = '{"kind": "network_title", "query": "QC/T 1036—2016 的中文名称是什么？", "must_include": "中华人民共和国汽车行业标准", "source": "network", "assert_mode": "rich_answer", "source_url": "https://max.book118.com/html/2023/0809/6104213203005211.shtm"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_5() -> None:
    case = '{"kind": "network_title_variant", "query": "QC/T 1036—2016 的名称或公开标题是什么？", "must_include": "Automotive DC-AC power inverter", "source": "network", "assert_mode": "rich_answer", "source_url": "https://max.book118.com/html/2023/0809/6104213203005211.shtm"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_6() -> None:
    case = '{"kind": "network_title_variant", "query": "QC/T 1036—2016 的名称或公开标题是什么？", "must_include": "汽车电源逆变器", "source": "network", "assert_mode": "rich_answer", "source_url": "https://max.book118.com/html/2023/0809/6104213203005211.shtm"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_7() -> None:
    case = '{"kind": "page_coverage", "query": "第1页 # 中华人民共和国汽车行业标准 QC/T 1036—2016 汽车电源逆变器...", "must_include": "# 中华人民共和国汽车行业标准 QC/T 1036—2016 汽车电源逆变器...", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_8() -> None:
    case = '{"kind": "page_coverage", "query": "第2页 以上机械行业标准由机械工业出版社出版，汽车行业标准由科学技术文献出版社出版...", "must_include": "以上机械行业标准由机械工业出版社出版，汽车行业标准由科学技术文献出版社出版...", "source": "local", "assert_mode": "context_contains", "page_no": 2}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_9() -> None:
    case = '{"kind": "page_coverage", "query": "第4页 QC/T 753—2016", "must_include": "QC/T 753—2016", "source": "local", "assert_mode": "context_contains", "page_no": 4}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_10() -> None:
    case = '{"kind": "page_coverage", "query": "第5页 QC/T 29078—2016", "must_include": "QC/T 29078—2016", "source": "local", "assert_mode": "context_contains", "page_no": 5}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_11() -> None:
    case = '{"kind": "page_coverage", "query": "第6页 ## 目 次 前言 …… II 1 范围 …… 1 2 规范性引用文件 ……...", "must_include": "## 目 次 前言 …… II 1 范围 …… 1 2 规范性引用文件 ……...", "source": "local", "assert_mode": "context_contains", "page_no": 6}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_12() -> None:
    case = '{"kind": "page_coverage", "query": "第7页 本标准起草单位：上海汽车集团股份有限公司技术中心、长沙汽车电器研究所、上海坤...", "must_include": "本标准起草单位：上海汽车集团股份有限公司技术中心、长沙汽车电器研究所、上海坤...", "source": "local", "assert_mode": "context_contains", "page_no": 7}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_13() -> None:
    case = '{"kind": "page_coverage", "query": "第8页 GB 1002—2008 家用和类似用途单相插头插座型式、基本参数和尺寸 G...", "must_include": "GB 1002—2008 家用和类似用途单相插头插座型式、基本参数和尺寸 G...", "source": "local", "assert_mode": "context_contains", "page_no": 8}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_14() -> None:
    case = '{"kind": "page_coverage", "query": "第9页 GB/T 30038 道路车辆 电气电子设备防护等级(IP代码) GB/T...", "must_include": "GB/T 30038 道路车辆 电气电子设备防护等级(IP代码) GB/T...", "source": "local", "assert_mode": "context_contains", "page_no": 9}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_15() -> None:
    case = '{"kind": "page_coverage", "query": "第12页 输入电路对交流接地，输入电路对输出电路和输出电路对交流接地应承受1500 V...", "must_include": "输入电路对交流接地，输入电路对输出电路和输出电路对交流接地应承受1500 V...", "source": "local", "assert_mode": "context_contains", "page_no": 12}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_16() -> None:
    case = '{"kind": "page_coverage", "query": "第15页 ### 4.22 耐久性 逆变器应能承受7500次的开启循环试验，试验后的逆...", "must_include": "### 4.22 耐久性 逆变器应能承受7500次的开启循环试验，试验后的逆...", "source": "local", "assert_mode": "context_contains", "page_no": 15}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_17() -> None:
    case = '{"kind": "page_coverage", "query": "第16页 逆变器输出端连接100%额定输出功率的阻性负载，分别测量直流输入功率和交流输...", "must_include": "逆变器输出端连接100%额定输出功率的阻性负载，分别测量直流输入功率和交流输...", "source": "local", "assert_mode": "context_contains", "page_no": 16}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_18() -> None:
    case = '{"kind": "page_coverage", "query": "第18页 按照 4.6.3.1 及 4.6.5 的进入保护条件使逆变器关闭，当关闭条件...", "must_include": "按照 4.6.3.1 及 4.6.5 的进入保护条件使逆变器关闭，当关闭条件...", "source": "local", "assert_mode": "context_contains", "page_no": 18}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_19() -> None:
    case = '{"kind": "page_coverage", "query": "第19页 ### 5.15 湿热循环试验 逆变器按照 GB/T 28046.4—201...", "must_include": "### 5.15 湿热循环试验 逆变器按照 GB/T 28046.4—201...", "source": "local", "assert_mode": "context_contains", "page_no": 19}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_20() -> None:
    case = '{"kind": "page_coverage", "query": "第21页 按 GB 4343.1—2009 中第 5 章的试验方法对交流输出端口对 $...", "must_include": "按 GB 4343.1—2009 中第 5 章的试验方法对交流输出端口对 $...", "source": "local", "assert_mode": "context_contains", "page_no": 21}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_21() -> None:
    case = '{"kind": "standard", "query": "QC/T 1036—2016 的标准号和实施日期是什么？", "must_include": "QC/T 1036—2016", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_22() -> None:
    case = '{"kind": "standard", "query": "QC/T 1036—2016 对应的标准编号是什么？", "must_include": "QC/T 1036—2016", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_23() -> None:
    case = '{"kind": "standard", "query": "QC/T 1036—2016 的现行标准号是什么？", "must_include": "QC/T 1036—2016", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_24() -> None:
    case = '{"kind": "publication_date", "query": "QC/T 1036—2016 是哪一天发布的？", "must_include": "2016-04-05", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_25() -> None:
    case = '{"kind": "effective_date", "query": "QC/T 1036—2016 从哪一天开始实施？", "must_include": "2016-09-01", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_26() -> None:
    case = '{"kind": "section", "query": "在QC/T 1036—2016中，是否包含“中华人民共和国汽车行业标准”这一章节？", "must_include": "中华人民共和国汽车行业标准", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_27() -> None:
    case = '{"kind": "section", "query": "在QC/T 1036—2016中，是否包含“3.3”这一章节？", "must_include": "3.3", "source": "local", "assert_mode": "context_contains", "page_no": 9}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000007_golden_28() -> None:
    case = '{"kind": "section", "query": "在QC/T 1036—2016中，是否包含“4.6.4.1 绝缘电阻。”这一章节？", "must_include": "4.6.4.1 绝缘电阻。", "source": "local", "assert_mode": "context_contains", "page_no": 12}'
    _assert_case(json.loads(case))
