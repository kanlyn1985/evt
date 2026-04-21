from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import httpx


ALLOWED_QUERY_TYPES = {
    "definition",
    "standard_lookup",
    "lifecycle_lookup",
    "comparison",
    "timing_lookup",
    "parameter_lookup",
    "constraint",
    "section_lookup",
    "scope",
    "general_search",
    "no_answer_candidate",
}

SEMANTIC_PARSER_PROMPT_VERSION = "v1.0.0"

SEMANTIC_PARSER_SYSTEM_PROMPT = """你是企业知识库的查询语义解析器。

你的唯一职责是把外部自然语言问题解析成稳定、可机器消费的结构化查询对象。

你不是答案生成器，不要回答问题，不要总结文档内容，不要推测知识库中一定存在某条事实。
你只能基于问题本身做语义理解，并输出 JSON。

输出规则：
1. 只输出单个 JSON 对象，不要输出解释、前后缀、markdown 代码块。
2. query_type 只能是以下之一：
   definition, standard_lookup, lifecycle_lookup, comparison, timing_lookup,
   parameter_lookup, constraint, section_lookup, scope, general_search, no_answer_candidate
3. normalized_query 必须是去掉语气词、冗余问法后的核心查询。
4. target_topic 必须是用户真正关注的知识主题，而不是整句照抄。
5. answer_shape 只能使用：
   definition, list, process, requirement_set, table, value, freeform
6. aliases 只能放主题的等价表达、英文名、缩写或常见别称。
7. must_terms 只能放必须保留的实体词、缩写、标准号或主题锚点。
8. should_terms 只能放辅助检索的主题词，不要堆无意义近义词。
9. confidence 输出 0 到 1 的浮点数。

判定原则：
- 问“是什么/定义/如何理解”时，优先 definition。
- 问“有哪些类型/种类/包括哪些/分为哪些”时，优先 comparison。
- 问“流程/时序/阶段/状态转换/握手/预充/停机”时，优先 timing_lookup。
- 问“参数/阻值/电压/电流/频率/检测点/占空比”时，优先 parameter_lookup。
- 问“有什么要求/应满足什么/应符合什么/不应超过什么/不小于什么”时，优先 constraint。
- 如果问题没有明确语义目标，再退到 general_search。

通用性要求：
- 不要靠单个词做机械匹配，要尽量抽象出问题真正的主题对象。
- 不要把整句原样塞进 target_topic。
- 如果问题里包含英文缩写和中文主题，两者都要合理保留到 target_topic / aliases / must_terms 中。
- 如果问题明显无有效内容，才输出 no_answer_candidate。

你必须严格输出 JSON，不允许输出任何额外文本。"""


@dataclass(frozen=True)
class SemanticQuery:
    query_type: str
    normalized_query: str
    target_topic: str
    answer_shape: str
    aliases: list[str]
    must_terms: list[str]
    should_terms: list[str]
    confidence: float
    used_llm: bool
    raw_response: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_astron_settings() -> tuple[str, str, str]:
    _load_env_file(_project_root() / ".env")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    api_base = os.environ.get("ANTHROPIC_BASE_URL", "https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic")
    model = os.environ.get("ANTHROPIC_MODEL", "astron-code-latest")
    if not auth_token:
        raise RuntimeError("astron query semantic parser configuration unavailable")
    return api_base.rstrip("/"), auth_token, model


def _extract_json_block(content: str) -> dict[str, object]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        text = match.group(0)
    return json.loads(text)


def _sanitize_string_list(value: object, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items[:limit]


def _default_semantic(query: str) -> SemanticQuery:
    normalized = query.strip()
    return SemanticQuery(
        query_type="general_search" if normalized else "no_answer_candidate",
        normalized_query=normalized,
        target_topic=normalized,
        answer_shape="freeform",
        aliases=[],
        must_terms=[],
        should_terms=[],
        confidence=0.0,
        used_llm=False,
        raw_response=None,
    )


def _semantic_prompt(query: str) -> str:
    return (
        f"prompt_version: {SEMANTIC_PARSER_PROMPT_VERSION}\n"
        "请把下面这个用户问题解析成结构化 JSON。\n"
        "字段要求：\n"
        "- query_type: 只能是 definition, standard_lookup, lifecycle_lookup, comparison, timing_lookup, "
        "parameter_lookup, constraint, section_lookup, scope, general_search, no_answer_candidate 之一\n"
        "- normalized_query: 去掉语气和冗余后的核心查询\n"
        "- target_topic: 用户真正关注的主题对象\n"
        "- answer_shape: one_of(definition, list, process, requirement_set, table, value, freeform)\n"
        "- aliases: 主题的等价表达、英文或缩写\n"
        "- must_terms: 必须保留的实体词或缩写\n"
        "- should_terms: 可以辅助检索的主题词\n"
        "- confidence: 0 到 1 的浮点数\n"
        f"用户问题：{query}"
    )


def _call_astron_text(prompt: str) -> str:
    api_base, auth_token, model = _load_astron_settings()
    timeout_ms = int(os.environ.get("API_TIMEOUT_MS", "600000"))
    timeout_sec = min(timeout_ms / 1000.0, 40.0)
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 1000,
        "temperature": 0,
        "system": SEMANTIC_PARSER_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    response = httpx.post(
        f"{api_base}/v1/messages",
        headers=headers,
        json=payload,
        timeout=timeout_sec,
    )
    response.raise_for_status()
    data = response.json()
    content_blocks = data.get("content", [])
    if isinstance(content_blocks, list):
        content = "\n".join(
            str(item.get("text", "")).strip()
            for item in content_blocks
            if isinstance(item, dict) and item.get("type") == "text"
        ).strip()
    else:
        content = ""
    if not content:
        raise RuntimeError("semantic parser llm returned empty content")
    return str(content).strip()


@lru_cache(maxsize=512)
def parse_semantic_query(query: str) -> SemanticQuery:
    stripped = query.strip()
    if not stripped:
        return _default_semantic(query)

    try:
        raw = _call_astron_text(_semantic_prompt(stripped))
        payload = _extract_json_block(raw)
        query_type = str(payload.get("query_type") or "").strip()
        if query_type not in ALLOWED_QUERY_TYPES:
            query_type = "general_search"
        normalized_query = str(payload.get("normalized_query") or stripped).strip() or stripped
        target_topic = str(payload.get("target_topic") or normalized_query).strip() or normalized_query
        answer_shape = str(payload.get("answer_shape") or "freeform").strip() or "freeform"
        aliases = _sanitize_string_list(payload.get("aliases"))
        must_terms = _sanitize_string_list(payload.get("must_terms"))
        should_terms = _sanitize_string_list(payload.get("should_terms"))
        confidence = float(payload.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        return SemanticQuery(
            query_type=query_type,
            normalized_query=normalized_query,
            target_topic=target_topic,
            answer_shape=answer_shape,
            aliases=aliases,
            must_terms=must_terms,
            should_terms=should_terms,
            confidence=confidence,
            used_llm=True,
            raw_response=raw,
        )
    except Exception:
        return _default_semantic(query)
