from __future__ import annotations


POLICY_BY_QUERY_TYPE = {
    "definition": "definition",
    "standard_lookup": "standard_lookup",
    "lifecycle_lookup": "lifecycle_lookup",
    "section_lookup": "section_lookup",
    "comparison": "comparison",
    "general_search": "general_search",
    "scope": "general_search",
    "constraint": "general_search",
    "no_answer_candidate": "no_answer_candidate",
}


def select_answer_policy(query_type: str) -> str:
    return POLICY_BY_QUERY_TYPE.get(query_type, "general_search")


def build_summary_lines(
    *,
    policy: str,
    documents: list[dict[str, object]],
    facts: list[dict[str, object]],
    evidence: list[dict[str, object]],
    fact_summaries: list[str],
) -> list[str]:
    lines: list[str] = []
    if policy == "no_answer_candidate":
        return ["没有找到足够的结构化结果。"]

    if not facts and not evidence:
        return ["没有找到足够的结构化结果。"]

    if documents:
        top_doc = documents[0]
        lines.append(f"命中文档: {top_doc['source_filename']} ({top_doc['doc_id']})")

    if fact_summaries:
        lines.extend(fact_summaries)
    elif evidence:
        if policy in {"definition", "section_lookup"}:
            lines.append("当前主要依据证据片段匹配，尚未形成足够多的结构化事实。")
        else:
            lines.append("当前主要依据证据片段匹配，尚未形成足够多的结构化事实。")
    else:
        lines.append("没有找到足够的结构化结果。")

    return lines


def build_direct_answer(
    *,
    policy: str,
    query: str,
    facts: list[dict[str, object]],
    evidence: list[dict[str, object]],
    wiki_pages: list[dict[str, object]],
    standard_normalizer,
    standard_extractor,
    truncate_fn,
) -> str:
    if policy == "definition":
        for item in facts:
            if item["fact_type"] in {"term_definition", "concept_definition"} and isinstance(item["object"], dict):
                term = item["object"].get("term", "")
                definition = item["object"].get("definition", "")
                if term and definition:
                    return f"{term}: {definition}"
            if item["fact_type"] == "document_abstract" and isinstance(item["object"], dict):
                value = item["object"].get("value", "")
                if value:
                    return truncate_fn(str(value), 240)

    if policy in {"standard_lookup", "lifecycle_lookup"}:
        query_standard = standard_normalizer(standard_extractor(query))
        standard = None
        effective = None
        publication = None
        replaced = None
        for item in facts:
            if not isinstance(item["object"], dict):
                continue
            if item["fact_type"] == "document_standard" and standard is None:
                standard = item["object"].get("value")
            elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "effective_date" and effective is None:
                effective = item["object"].get("value")
            elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "publication_date" and publication is None:
                publication = item["object"].get("value")
            elif item["fact_type"] == "document_versioning" and replaced is None:
                replaced = item["object"].get("value")
        if not standard or standard_normalizer(str(standard)) != query_standard:
            for item in wiki_pages:
                title = str(item.get("title", ""))
                if standard_normalizer(title) == query_standard:
                    standard = title
                    break
        parts = []
        if standard:
            parts.append(f"标准号是 {standard}")
        if publication:
            parts.append(f"发布日期是 {publication}")
        if effective:
            parts.append(f"实施日期是 {effective}")
        if replaced:
            parts.append(f"代替标准是 {replaced}")
        if parts:
            return "，".join(parts) + "。"

    if policy == "comparison":
        comparison_answer = _build_comparison_answer(query, facts, evidence)
        if comparison_answer:
            return comparison_answer

    requirement_answer = _build_requirement_answer(query, facts)
    if requirement_answer:
        return requirement_answer

    if facts:
        first = facts[0]
        if isinstance(first.get("object"), dict):
            obj = first["object"]
            if "title" in obj:
                return f"最相关的结构化结果是章节《{obj['title']}》。"
            if "value" in obj:
                return f"最相关的结构化结果是 {obj['value']}。"

    if evidence:
        return evidence[0]["snippet"]

    return "没有找到足够的结构化结果。"


def _build_comparison_answer(
    query: str,
    facts: list[dict[str, object]],
    evidence: list[dict[str, object]],
) -> str:
    if "V2X" not in query.upper():
        return ""

    relation_items: list[str] = []
    for item in facts:
        if item.get("fact_type") != "comparison_relation":
            continue
        payload = item.get("object")
        if isinstance(payload, dict) and str(payload.get("subject", "")).upper() == "V2X":
            value = str(payload.get("item", "")).strip()
            if value and value not in relation_items:
                relation_items.append(value)
    if relation_items:
        return "当前知识库中，V2X 涉及的对象/类型至少包括：" + "、".join(relation_items) + "。"

    text_parts = [item.get("snippet", "") for item in evidence]
    combined = "\n".join(str(part) for part in text_parts if part)
    if not combined:
        return ""

    variants: list[str] = []
    patterns = [
        r"(V2X)",
        r"(V2G)",
        r"(vehicle to grid|vehicle-to-grid)",
        r"(电动汽车与电网充放电双向互动)",
        r"(公共电网)",
        r"(楼宇供配电系统)",
        r"(住宅供配电系统)",
        r"(电动汽车动力蓄电池)",
        r"(用电负荷)",
    ]
    for pattern in patterns:
        for match in __import__("re").finditer(pattern, combined, __import__("re").I):
            value = match.group(0).strip()
            if value and value not in variants:
                variants.append(value)

    normalized_variants: list[str] = []
    for value in variants:
        normalized = value
        lowered = value.lower()
        if lowered in {"vehicle to grid", "vehicle-to-grid"}:
            normalized = "V2G"
        if normalized not in normalized_variants:
            normalized_variants.append(normalized)

    if any(item in normalized_variants for item in ("公共电网", "楼宇供配电系统", "住宅供配电系统", "电动汽车动力蓄电池", "用电负荷")):
        return "V2X 可覆盖的对象至少包括：公共电网、楼宇供配电系统、住宅供配电系统、电动汽车动力蓄电池、用电负荷。"
    if "V2G" in normalized_variants:
        return "当前知识库已明确命中的 V2X 相关类型是 V2G；更广义的对象还包括公共电网、楼宇供配电系统、住宅供配电系统、电动汽车动力蓄电池、用电负荷。"
    return ""


def _build_requirement_answer(query: str, facts: list[dict[str, object]]) -> str:
    if "表" in query and any(token in query for token in ("字段", "列", "表头", "参数")):
        for item in facts:
            if item.get("fact_type") == "table_requirement" and isinstance(item.get("object"), dict):
                payload = item["object"]
                title = str(payload.get("table_title") or payload.get("title") or "").strip()
                headers = payload.get("headers") or []
                rows = payload.get("rows") or []
                if headers:
                    preview = "；".join(str(cell) for cell in rows[0]) if rows else ""
                    return f"{title or '该表'} 的字段包括：{'、'.join(str(h) for h in headers)}。{('示例行：' + preview + '。') if preview else ''}"

    for item in facts:
        if item.get("fact_type") == "requirement" and isinstance(item.get("object"), dict):
            payload = item["object"]
            content = str(payload.get("content", "")).strip()
            threshold = str(payload.get("threshold", "")).strip()
            subject = str(payload.get("subject", "")).strip()
            if content:
                if threshold and threshold not in content:
                    return f"{subject or '该要求'}：{content} 其中关键阈值为 {threshold}。"
                return content
        if item.get("fact_type") == "table_requirement" and isinstance(item.get("object"), dict):
            payload = item["object"]
            title = str(payload.get("table_title") or payload.get("title") or "").strip()
            headers = payload.get("headers") or []
            rows = payload.get("rows") or []
            if headers and rows:
                first_row = "；".join(str(cell) for cell in rows[0])
                return f"{title or '表格要求'}：字段包括 {'、'.join(str(h) for h in headers)}。示例行：{first_row}。"
        if item.get("fact_type") == "threshold" and isinstance(item.get("object"), dict):
            payload = item["object"]
            subject = str(payload.get("subject", "")).strip()
            value = str(payload.get("value", "")).strip()
            if subject and value:
                return f"{subject} 的关键阈值是 {value}。"
    return ""
