from __future__ import annotations

import pytest

from enterprise_agent_kb.facts import _extract_term_definitions


@pytest.mark.unit
def test_extract_term_definitions_from_term_page() -> None:
    text = """
### 3.3 功能 function

#### 3.3.1

## 控制导引电路 control pilot circuit

设计用于电动汽车和供电设备之间信号传输或通信的电路。

注：对于模式2，控制导引电路是电动汽车与缆上控制与保护装置之间信号传输或通信的电路。

#### 3.3.2

## 控制导引功能 control pilot function；CP

用于监控电动汽车和供电设备之间交互的功能。
"""
    items = _extract_term_definitions(text)
    terms = {item[2]["term"]: item[2]["definition"] for item in items}

    assert "控制导引电路 control pilot circuit" in terms
    assert "设计用于电动汽车和供电设备之间信号传输或通信的电路。" in terms["控制导引电路 control pilot circuit"]
    assert "控制导引功能 control pilot function;CP" in terms


@pytest.mark.unit
def test_extract_term_definitions_rejects_revision_bullets() -> None:
    text = """
本文件代替 GB/T 18487.1—2015。

s）增加了模式2和3使用数字通信的适用性要求（见第6章）；

t）将电击防护的一般要求更改为通则。
"""
    items = _extract_term_definitions(text)
    assert items == []
