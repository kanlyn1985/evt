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
def test_doc_000008_golden_1() -> None:
    case = '{"kind": "network_standard", "query": "IEC 33020 的标准号是什么？", "must_include": "IEC 33020", "source": "network", "assert_mode": "rich_answer", "source_url": "https://www.scribd.com/document/845071770/AutomotiveSPICE-PAM-40-Chinese过程评估模型"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_2() -> None:
    case = '{"kind": "page_coverage", "query": "第1页 # Automotive SPICE $ ^{®} $ Process Re...", "must_include": "# Automotive SPICE $ ^{®} $ Process Re...", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_3() -> None:
    case = '{"kind": "page_coverage", "query": "第2页 # Automotive SPICE $ ^{®} $ 过程参考模型 过程评...", "must_include": "# Automotive SPICE $ ^{®} $ 过程参考模型 过程评...", "source": "local", "assert_mode": "context_contains", "page_no": 2}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_4() -> None:
    case = '{"kind": "page_coverage", "query": "第3页 This document reproduces relevant mate...", "must_include": "This document reproduces relevant mate...", "source": "local", "assert_mode": "context_contains", "page_no": 3}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_5() -> None:
    case = '{"kind": "page_coverage", "query": "第6页 ## 衍生著作 未经 VDA 质量管理中心的事先同意，不得更改、转换或扩展本...", "must_include": "## 衍生著作 未经 VDA 质量管理中心的事先同意，不得更改、转换或扩展本...", "source": "local", "assert_mode": "context_contains", "page_no": 6}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_6() -> None:
    case = '{"kind": "page_coverage", "query": "第7页 ## Trademark notice Automotive SPICE $...", "must_include": "## Trademark notice Automotive SPICE $...", "source": "local", "assert_mode": "context_contains", "page_no": 7}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_7() -> None:
    case = '{"kind": "page_coverage", "query": "第8页 ## 商标声明 Automotive SPICE $ ^{®} $是 Ver...", "must_include": "## 商标声明 Automotive SPICE $ ^{®} $是 Ver...", "source": "local", "assert_mode": "context_contains", "page_no": 8}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_8() -> None:
    case = '{"kind": "page_coverage", "query": "第9页 Document distribution.....", "must_include": "Document distribution.....", "source": "local", "assert_mode": "context_contains", "page_no": 9}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_9() -> None:
    case = '{"kind": "page_coverage", "query": "第10页 过程能力等级和过程属性 .....", "must_include": "过程能力等级和过程属性 .....", "source": "local", "assert_mode": "context_contains", "page_no": 10}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_10() -> None:
    case = '{"kind": "page_coverage", "query": "第11页 System engineering process group (SYS)...", "must_include": "System engineering process group (SYS)...", "source": "local", "assert_mode": "context_contains", "page_no": 11}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_11() -> None:
    case = '{"kind": "page_coverage", "query": "第12页 ## VDA QMC ## AUTOMOTIVE SPICE $ ^{®}...", "must_include": "## VDA QMC ## AUTOMOTIVE SPICE $ ^{®}...", "source": "local", "assert_mode": "context_contains", "page_no": 12}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_12() -> None:
    case = '{"kind": "page_coverage", "query": "第13页 Process capability levels and process...", "must_include": "Process capability levels and process...", "source": "local", "assert_mode": "context_contains", "page_no": 13}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_13() -> None:
    case = '{"kind": "page_coverage", "query": "第14页 ## VDA QMC ## AUTOMOTIVE SPICE $ ^{®}...", "must_include": "## VDA QMC ## AUTOMOTIVE SPICE $ ^{®}...", "source": "local", "assert_mode": "context_contains", "page_no": 14}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_14() -> None:
    case = '{"kind": "page_coverage", "query": "第15页 “Involved Party” (Level 2).....173 Ter...", "must_include": "“Involved Party” (Level 2).....173 Ter...", "source": "local", "assert_mode": "context_contains", "page_no": 15}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_15() -> None:
    case = '{"kind": "page_coverage", "query": "第16页 173 术语 - “Verification（验证）”代替“Testing（...", "must_include": "173 术语 - “Verification（验证）”代替“Testing（...", "source": "local", "assert_mode": "context_contains", "page_no": 16}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_16() -> None:
    case = '{"kind": "page_coverage", "query": "第17页 The Automotive SPICE process assessmen...", "must_include": "The Automotive SPICE process assessmen...", "source": "local", "assert_mode": "context_contains", "page_no": 17}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_17() -> None:
    case = '{"kind": "page_coverage", "query": "第18页 Automotive SPICE 有其本身的过程参考模型(PRM)，是基于...", "must_include": "Automotive SPICE 有其本身的过程参考模型(PRM)，是基于...", "source": "local", "assert_mode": "context_contains", "page_no": 18}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_18() -> None:
    case = '{"kind": "page_coverage", "query": "第19页 Often used more narrowly in reference...", "must_include": "Often used more narrowly in reference...", "source": "local", "assert_mode": "context_contains", "page_no": 19}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_19() -> None:
    case = '{"kind": "page_coverage", "query": "第20页 一功能的硬件元器件逻辑性组合（例如功能块）", "must_include": "一功能的硬件元器件逻辑性组合（例如功能块）", "source": "local", "assert_mode": "context_contains", "page_no": 20}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_20() -> None:
    case = '{"kind": "page_coverage", "query": "第21页 Examples: learning rate, loss function...", "must_include": "Examples: learning rate, loss function...", "source": "local", "assert_mode": "context_contains", "page_no": 21}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_21() -> None:
    case = '{"kind": "page_coverage", "query": "第22页 超参数 Automotive SPICE V4.0 在机...", "must_include": "超参数 Automotive SPICE V4.0 在机...", "source": "local", "assert_mode": "context_contains", "page_no": 22}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_22() -> None:
    case = '{"kind": "page_coverage", "query": "第23页 System elements can be further decompo...", "must_include": "System elements can be further decompo...", "source": "local", "assert_mode": "context_contains", "page_no": 23}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_23() -> None:
    case = '{"kind": "page_coverage", "query": "第24页 0 验证是通过提供客观证据来确认一个要素满", "must_include": "0 验证是通过提供客观证据来确认一个要素满", "source": "local", "assert_mode": "context_contains", "page_no": 24}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_24() -> None:
    case = '{"kind": "page_coverage", "query": "第25页 #### 1.3. Abbreviations BP B...", "must_include": "#### 1.3. Abbreviations BP B...", "source": "local", "assert_mode": "context_contains", "page_no": 25}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_25() -> None:
    case = '{"kind": "page_coverage", "query": "第26页 #### 1.3. 缩略语 BP Base Practi...", "must_include": "#### 1.3. 缩略语 BP Base Practi...", "source": "local", "assert_mode": "context_contains", "page_no": 26}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_26() -> None:
    case = '{"kind": "page_coverage", "query": "第33页 SYS.1 Requirements Elicitation SYS.2 S...", "must_include": "SYS.1 Requirements Elicitation SYS.2 S...", "source": "local", "assert_mode": "context_contains", "page_no": 33}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_27() -> None:
    case = '{"kind": "page_coverage", "query": "第34页 ### SPL.2 产品发布 表 4 — 主要生命周期过程 - SPL 过程...", "must_include": "### SPL.2 产品发布 表 4 — 主要生命周期过程 - SPL 过程...", "source": "local", "assert_mode": "context_contains", "page_no": 34}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_28() -> None:
    case = '{"kind": "page_coverage", "query": "第35页 MLE.1 Machine Learning Requirements An...", "must_include": "MLE.1 Machine Learning Requirements An...", "source": "local", "assert_mode": "context_contains", "page_no": 35}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_29() -> None:
    case = '{"kind": "page_coverage", "query": "第36页 MLE.1 机器学习需求分析 MLE.2 机器学习架构 MLE.3 机器学习...", "must_include": "MLE.1 机器学习需求分析 MLE.2 机器学习架构 MLE.3 机器学习...", "source": "local", "assert_mode": "context_contains", "page_no": 36}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_30() -> None:
    case = '{"kind": "page_coverage", "query": "第37页 ### PIM.3 Process Improvement Table 12...", "must_include": "### PIM.3 Process Improvement Table 12...", "source": "local", "assert_mode": "context_contains", "page_no": 37}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_31() -> None:
    case = '{"kind": "page_coverage", "query": "第47页 In principle the three rating methods...", "must_include": "In principle the three rating methods...", "source": "local", "assert_mode": "context_contains", "page_no": 47}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_32() -> None:
    case = '{"kind": "page_coverage", "query": "第48页 原则上，ISO/IEC 33020 中定义的三种评定方法依赖于 a）是否只对...", "must_include": "原则上，ISO/IEC 33020 中定义的三种评定方法依赖于 a）是否只对...", "source": "local", "assert_mode": "context_contains", "page_no": 48}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_33() -> None:
    case = '{"kind": "page_coverage", "query": "第50页 过程能力等级模型 根据错误!未找到引用源。所定义的过程能力等级模型，过程所达...", "must_include": "过程能力等级模型 根据错误!未找到引用源。所定义的过程能力等级模型，过程所达...", "source": "local", "assert_mode": "context_contains", "page_no": 50}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_34() -> None:
    case = '{"kind": "page_coverage", "query": "第51页 Assessment indicators According to ISO...", "must_include": "Assessment indicators According to ISO...", "source": "local", "assert_mode": "context_contains", "page_no": 51}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_35() -> None:
    case = '{"kind": "page_coverage", "query": "第52页 评估指标 根据 ISO/IEC 33004，过程评估模型需要定义一套评估指标...", "must_include": "评估指标 根据 ISO/IEC 33004，过程评估模型需要定义一套评估指标...", "source": "local", "assert_mode": "context_contains", "page_no": 52}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_36() -> None:
    case = '{"kind": "page_coverage", "query": "第55页 Information items versus work products...", "must_include": "Information items versus work products...", "source": "local", "assert_mode": "context_contains", "page_no": 55}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_37() -> None:
    case = '{"kind": "page_coverage", "query": "第56页 理解信息项和工作产品 为了判断过程成果和过程属性成就的存在或缺失，评估需要获...", "must_include": "理解信息项和工作产品 为了判断过程成果和过程属性成就的存在或缺失，评估需要获...", "source": "local", "assert_mode": "context_contains", "page_no": 56}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_38() -> None:
    case = '{"kind": "page_coverage", "query": "第63页 Acquisition process group (ACQ) ######...", "must_include": "Acquisition process group (ACQ) ######...", "source": "local", "assert_mode": "context_contains", "page_no": 63}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_39() -> None:
    case = '{"kind": "page_coverage", "query": "第64页 获取过程组(ACO) ###### 4.1.1.", "must_include": "获取过程组(ACO) ###### 4.1.1.", "source": "local", "assert_mode": "context_contains", "page_no": 64}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_40() -> None:
    case = '{"kind": "page_coverage", "query": "第65页 Establish and maintain an agreement on...", "must_include": "Establish and maintain an agreement on...", "source": "local", "assert_mode": "context_contains", "page_no": 65}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_41() -> None:
    case = '{"kind": "page_coverage", "query": "第66页 ACQ.4.BP2: 交换所有约定的信息。使用客户和供应商之间定义的联合接口...", "must_include": "ACQ.4.BP2: 交换所有约定的信息。使用客户和供应商之间定义的联合接口...", "source": "local", "assert_mode": "context_contains", "page_no": 66}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_42() -> None:
    case = '{"kind": "page_coverage", "query": "第67页 Define the functionality to be include...", "must_include": "Define the functionality to be include...", "source": "local", "assert_mode": "context_contains", "page_no": 67}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_43() -> None:
    case = '{"kind": "page_coverage", "query": "第68页 供应过程组 (SPL) ###### 4.2.1.", "must_include": "供应过程组 (SPL) ###### 4.2.1.", "source": "local", "assert_mode": "context_contains", "page_no": 68}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_44() -> None:
    case = '{"kind": "page_coverage", "query": "第69页 Ensure a unique identification of the...", "must_include": "Ensure a unique identification of the...", "source": "local", "assert_mode": "context_contains", "page_no": 69}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_45() -> None:
    case = '{"kind": "page_coverage", "query": "第70页 • 注5:发布说明可包括有关法律方面的信息，如相关目标市场、考虑的法规等。另...", "must_include": "• 注5:发布说明可包括有关法律方面的信息，如相关目标市场、考虑的法规等。另...", "source": "local", "assert_mode": "context_contains", "page_no": 70}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_46() -> None:
    case = '{"kind": "page_coverage", "query": "第71页 ## AUTOMOTIVE SPICE $ ^{®} $...", "must_include": "## AUTOMOTIVE SPICE $ ^{®} $...", "source": "local", "assert_mode": "context_contains", "page_no": 71}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_47() -> None:
    case = '{"kind": "page_coverage", "query": "第72页 ## AUTOMOTIVE SPICE $ ^{®} $...", "must_include": "## AUTOMOTIVE SPICE $ ^{®} $...", "source": "local", "assert_mode": "context_contains", "page_no": 72}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_48() -> None:
    case = '{"kind": "page_coverage", "query": "第73页 Obtain and define stakeholder expectat...", "must_include": "Obtain and define stakeholder expectat...", "source": "local", "assert_mode": "context_contains", "page_no": 73}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_49() -> None:
    case = '{"kind": "page_coverage", "query": "第74页 系统工程过程组 (SYS) ###### 4.3.1.", "must_include": "系统工程过程组 (SYS) ###### 4.3.1.", "source": "local", "assert_mode": "context_contains", "page_no": 74}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_50() -> None:
    case = '{"kind": "page_coverage", "query": "第75页 Note 4: Requirements changes may arise...", "must_include": "Note 4: Requirements changes may arise...", "source": "local", "assert_mode": "context_contains", "page_no": 75}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_51() -> None:
    case = '{"kind": "page_coverage", "query": "第76页 # AUTOMOTIVE SPICE $ ^{®} $...", "must_include": "# AUTOMOTIVE SPICE $ ^{®} $...", "source": "local", "assert_mode": "context_contains", "page_no": 76}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_52() -> None:
    case = '{"kind": "page_coverage", "query": "第78页 ###### 4.3.2. SYS.2 系统需求分析 过...", "must_include": "###### 4.3.2. SYS.2 系统需求分析 过...", "source": "local", "assert_mode": "context_contains", "page_no": 78}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_53() -> None:
    case = '{"kind": "page_coverage", "query": "第80页 SYS.2.BP3: 分析系统需求。分析已定义的系统需求（包括它们的相互依赖...", "must_include": "SYS.2.BP3: 分析系统需求。分析已定义的系统需求（包括它们的相互依赖...", "source": "local", "assert_mode": "context_contains", "page_no": 80}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_54() -> None:
    case = '{"kind": "page_coverage", "query": "第81页 BP3: Analyze system requirem...", "must_include": "BP3: Analyze system requirem...", "source": "local", "assert_mode": "context_contains", "page_no": 81}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_55() -> None:
    case = '{"kind": "page_coverage", "query": "第82页 BP3: 分析系统需求 X BP4: 分析对系统环境的影...", "must_include": "BP3: 分析系统需求 X BP4: 分析对系统环境的影...", "source": "local", "assert_mode": "context_contains", "page_no": 82}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_56() -> None:
    case = '{"kind": "page_coverage", "query": "第84页 ###### 4.3.3. SYS.3 系统架构设计 过...", "must_include": "###### 4.3.3. SYS.3 系统架构设计 过...", "source": "local", "assert_mode": "context_contains", "page_no": 84}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_57() -> None:
    case = '{"kind": "page_coverage", "query": "第86页 注 $ ^{5} $: 适合分析技术方面方法的示例如，原型、仿真和定性分析(...", "must_include": "注 $ ^{5} $: 适合分析技术方面方法的示例如，原型、仿真和定性分析(...", "source": "local", "assert_mode": "context_contains", "page_no": 86}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_58() -> None:
    case = '{"kind": "page_coverage", "query": "第87页 BP3: Analyze the system arch...", "must_include": "BP3: Analyze the system arch...", "source": "local", "assert_mode": "context_contains", "page_no": 87}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_59() -> None:
    case = '{"kind": "page_coverage", "query": "第88页 BP3: 分析系统架构 X BP4: 确保一致性和建立双...", "must_include": "BP3: 分析系统架构 X BP4: 确保一致性和建立双...", "source": "local", "assert_mode": "context_contains", "page_no": 88}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_60() -> None:
    case = '{"kind": "page_coverage", "query": "第89页 Specify the verification measures, bas...", "must_include": "Specify the verification measures, bas...", "source": "local", "assert_mode": "context_contains", "page_no": 89}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_61() -> None:
    case = '{"kind": "page_coverage", "query": "第90页 ## 基本实践 SYS.4.BP1: 定义系统集成的验证措施。依照系统架构的...", "must_include": "## 基本实践 SYS.4.BP1: 定义系统集成的验证措施。依照系统架构的...", "source": "local", "assert_mode": "context_contains", "page_no": 90}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_62() -> None:
    case = '{"kind": "page_coverage", "query": "第91页 Note 6: Providing all necessary inform...", "must_include": "Note 6: Providing all necessary inform...", "source": "local", "assert_mode": "context_contains", "page_no": 91}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_63() -> None:
    case = '{"kind": "page_coverage", "query": "第92页 ## AUTOMOTIVE SPICE $ ^{®} $ SYS.4.BP5...", "must_include": "## AUTOMOTIVE SPICE $ ^{®} $ SYS.4.BP5...", "source": "local", "assert_mode": "context_contains", "page_no": 92}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_64() -> None:
    case = '{"kind": "page_coverage", "query": "第93页 Specify the verification measures for...", "must_include": "Specify the verification measures for...", "source": "local", "assert_mode": "context_contains", "page_no": 93}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_65() -> None:
    case = '{"kind": "page_coverage", "query": "第94页 ###### 4.3.5. SYS.5 系统验证 过程...", "must_include": "###### 4.3.5. SYS.5 系统验证 过程...", "source": "local", "assert_mode": "context_contains", "page_no": 94}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_66() -> None:
    case = '{"kind": "page_coverage", "query": "第95页 Note 2: Examples for criteria for sele...", "must_include": "Note 2: Examples for criteria for sele...", "source": "local", "assert_mode": "context_contains", "page_no": 95}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_67() -> None:
    case = '{"kind": "page_coverage", "query": "第96页 一定意味着两者之间的信息是一致的", "must_include": "一定意味着两者之间的信息是一致的", "source": "local", "assert_mode": "context_contains", "page_no": 96}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_68() -> None:
    case = '{"kind": "page_coverage", "query": "第97页 ## AUTOMOTIVE SPICE $ ^{®} $...", "must_include": "## AUTOMOTIVE SPICE $ ^{®} $...", "source": "local", "assert_mode": "context_contains", "page_no": 97}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_69() -> None:
    case = '{"kind": "page_coverage", "query": "第98页 60 验证措施 X 03-50 验证措施数据", "must_include": "60 验证措施 X 03-50 验证措施数据", "source": "local", "assert_mode": "context_contains", "page_no": 98}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_70() -> None:
    case = '{"kind": "page_coverage", "query": "第99页 Note 2: Examples for defined character...", "must_include": "Note 2: Examples for defined character...", "source": "local", "assert_mode": "context_contains", "page_no": 99}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_71() -> None:
    case = '{"kind": "page_coverage", "query": "第100页 软件工程过程组 (SWE) ###### 4.4.1.", "must_include": "软件工程过程组 (SWE) ###### 4.4.1.", "source": "local", "assert_mode": "context_contains", "page_no": 100}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_72() -> None:
    case = '{"kind": "standard", "query": "IEC 33020 的标准号和实施日期是什么？", "must_include": "IEC 33020", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_73() -> None:
    case = '{"kind": "standard", "query": "IEC 33020 对应的标准编号是什么？", "must_include": "IEC 33020", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_74() -> None:
    case = '{"kind": "standard", "query": "IEC 33020 的现行标准号是什么？", "must_include": "IEC 33020", "source": "local", "assert_mode": "rich_answer"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_75() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“Automotive SPICE $ ^{®} $ Process Reference Model Process Assessment Model”这一章节？", "must_include": "Automotive SPICE $ ^{®} $ Process Reference Model Process Assessment Model", "source": "local", "assert_mode": "context_contains", "page_no": 1}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_76() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“Document history”这一章节？", "must_include": "Document history", "source": "local", "assert_mode": "context_contains", "page_no": 7}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_77() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“1. Introduction”这一章节？", "must_include": "1. Introduction", "source": "local", "assert_mode": "context_contains", "page_no": 17}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_78() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“1.3. 缩略语”这一章节？", "must_include": "1.3. 缩略语", "source": "local", "assert_mode": "context_contains", "page_no": 26}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_79() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“PIM.3 Process Improvement”这一章节？", "must_include": "PIM.3 Process Improvement", "source": "local", "assert_mode": "context_contains", "page_no": 37}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_80() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“3.3.2.1. Information items versus work products”这一章节？", "must_include": "3.3.2.1. Information items versus work products", "source": "local", "assert_mode": "context_contains", "page_no": 55}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_81() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“4.1. 获取过程组(ACO)”这一章节？", "must_include": "4.1. 获取过程组(ACO)", "source": "local", "assert_mode": "context_contains", "page_no": 64}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000008_golden_82() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“4.2. 供应过程组 (SPL)”这一章节？", "must_include": "4.2. 供应过程组 (SPL)", "source": "local", "assert_mode": "context_contains", "page_no": 68}'
    _assert_case(json.loads(case))
