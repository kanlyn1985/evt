from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .synonyms import expand_with_synonyms


@dataclass(frozen=True)
class RewrittenQuery:
    original_query: str
    normalized_query: str
    query_type: str
    aliases: list[str]
    must_terms: list[str]
    should_terms: list[str]
    negative_terms: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def rewrite_query(query: str) -> RewrittenQuery:
    original = query.strip()
    normalized = _normalize_query(original)
    query_type = _detect_query_type(original, normalized)
    must_terms = _must_terms(original, normalized, query_type)
    negative_terms = _negative_terms(original)
    aliases = _aliases(original, normalized, must_terms)
    should_terms = _should_terms(normalized, aliases, must_terms, negative_terms)

    return RewrittenQuery(
        original_query=original,
        normalized_query=normalized,
        query_type=query_type,
        aliases=aliases,
        must_terms=must_terms,
        should_terms=should_terms,
        negative_terms=negative_terms,
    )


def _normalize_query(query: str) -> str:
    text = query.strip()
    for pattern in (
        r"^\s*(.+?)\s*是怎么定义的\s*$",
        r"^\s*(.+?)\s*怎么定义\s*$",
        r"^\s*(.+?)\s*如何定义\s*$",
        r"^\s*(.+?)\s*是什么\s*$",
        r"^\s*什么是\s*(.+?)\s*$",
        r"^\s*(.+?)\s*如何理解\s*$",
        r"^\s*(.+?)\s*怎么理解\s*$",
    ):
        match = re.match(pattern, text)
        if match:
            text = next(group for group in match.groups() if group)
            break
    text = text.replace("？", " ").replace("?", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _detect_query_type(original_query: str, normalized_query: str) -> str:
    if not normalized_query:
        return "no_answer_candidate"
    if re.search(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)\b", original_query, re.I):
        if any(token in original_query for token in ("发布日期", "实施日期", "生效日期", "发布", "实施")):
            return "lifecycle_lookup"
        return "standard_lookup"
    if re.search(r"(有哪些类型|包括哪些类型|有哪些种类|包括哪些种类|包含哪些类型|分为哪些类型|类型有哪些|种类有哪些|分类有哪些)", original_query):
        return "comparison"
    if re.search(r"(有什么要求|要求是什么|应满足什么|应符合什么|不应超过什么|不小于什么)", original_query):
        return "constraint"
    if re.search(r"(什么是|是什么|定义|怎么定义|如何定义|是怎么定义的|如何理解|怎么理解)", original_query):
        return "definition"
    if re.search(r"(阻值|电阻|参数值)", original_query):
        return "section_lookup"
    if re.search(r"(表\s*\d+|表\d+|字段|参数|指标|效率|功率因数|允差)", original_query):
        return "section_lookup"
    if any(token in original_query for token in ("范围", "适用于", "适用范围")):
        return "scope"
    if any(token in original_query for token in ("参数", "表格", "表1", "表 1", "表2", "表 2", "输出特性", "功率因数", "效率")):
        return "section_lookup"
    if any(token in original_query for token in ("要求", "限制", "约束", "不得", "不应", "必须")):
        return "constraint"
    if any(token in original_query for token in ("比较", "区别", "差异", "相比")):
        return "comparison"
    if any(token in original_query for token in ("章节", "第几章", "哪一章", "目录")):
        return "section_lookup"
    return "general_search"


def _must_terms(original_query: str, normalized_query: str, query_type: str) -> list[str]:
    terms: list[str] = []
    standard_code = _extract_standard_code(original_query)
    if standard_code:
        terms.append(_normalize_standard_code(standard_code))
    exact_terms = re.findall(r"[A-Z][A-Z0-9/-]{1,}", original_query)
    for term in exact_terms:
        if term not in terms:
            terms.append(term)
    if query_type == "definition" and normalized_query and normalized_query not in terms:
        terms.append(normalized_query)
    if query_type in {"constraint", "section_lookup"} and normalized_query:
        for token in _extract_domain_terms(original_query):
            if token not in terms:
                terms.append(token)
    return terms


def _negative_terms(query: str) -> list[str]:
    negatives: list[str] = []
    if any(token in query for token in ("不是", "不包括", "无关", "排除")):
        negatives.extend([token for token in ("不是", "不包括", "无关", "排除") if token in query])
    return negatives


def _aliases(original_query: str, normalized_query: str, must_terms: list[str]) -> list[str]:
    alias_candidates: list[str] = []
    for seed in [original_query, normalized_query, *must_terms]:
        for alias in expand_with_synonyms(seed):
            if alias and alias not in alias_candidates and alias != original_query and alias != normalized_query:
                alias_candidates.append(alias)
    for match in re.finditer(r"(表\s*\d+)", original_query):
        raw = match.group(1)
        compact = re.sub(r"\s+", "", raw)
        spaced = raw[0] + " " + re.sub(r"\D+", "", raw)
        for variant in [compact, spaced]:
            if variant and variant not in alias_candidates:
                alias_candidates.append(variant)
    return alias_candidates[:12]


def _should_terms(
    normalized_query: str,
    aliases: list[str],
    must_terms: list[str],
    negative_terms: list[str],
) -> list[str]:
    terms: list[str] = []
    for item in [normalized_query, *aliases]:
        cleaned = item.strip()
        if (
            cleaned
            and cleaned not in terms
            and cleaned not in must_terms
            and cleaned not in negative_terms
        ):
            terms.append(cleaned)
    return terms[:12]


def _extract_standard_code(query: str) -> str | None:
    match = re.search(r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[—-]\d{2,4})?", query, re.I)
    return match.group(0) if match else None


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_domain_terms(query: str) -> list[str]:
    terms: list[str] = []
    for pattern in [
        r"(表\s*\d+)",
        r"(输出特性参数允差)",
        r"(额定输出效率)",
        r"(功率因数)",
        r"(材料)",
        r"(尺寸)",
        r"(插销拔出力)",
        r"(温升)",
        r"(绝缘电阻)",
        r"(保护门)",
    ]:
        for match in re.finditer(pattern, query):
            term = match.group(1).strip()
            if term and term not in terms:
                terms.append(term)
    return terms
