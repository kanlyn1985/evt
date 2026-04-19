from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id
from .knowledge_units import extract_knowledge_units, save_knowledge_units, save_knowledge_units_jsonl


@dataclass(frozen=True)
class FactsBuildResult:
    doc_id: str
    fact_count: int
    fact_types: dict[str, int]
    export_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_text(value: str) -> str:
    value = _normalize_ocr_text(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.strip() for line in value.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def _normalize_ocr_text(value: str) -> str:
    normalized = (
        value.replace("犌", "G")
        .replace("犅", "B")
        .replace("犜", "T")
    )
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = (
        normalized.replace("／", "/")
        .replace("—", "—")
        .replace("‐", "-")
        .replace("‑", "-")
        .replace("‒", "-")
        .replace("–", "-")
        .replace("﹣", "-")
        .replace("－", "-")
    )
    return normalized


STANDARD_CODE_PATTERN = re.compile(
    r"(?:GB/T|GB|ISO|IEC|SAE|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[-—]\d{2,4})?",
    re.I,
)


def _extract_doc_metadata(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    text = _normalize_ocr_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title_found = False
    for line in lines:
        if line.startswith("# "):
            results.append(("document_title", "title", {"value": line[2:].strip()}))
            title_found = True
            break

    standard_matches = STANDARD_CODE_PATTERN.findall(text)
    normalized_standard_matches = []
    for match in standard_matches:
        standard_code = match.strip()
        standard_code = re.sub(r"(?i)^GBT", "GB/T", standard_code)
        standard_code = re.sub(r"(?i)^GB/T(?=\d)", "GB/T ", standard_code)
        standard_code = re.sub(r"(?i)^GB(?=\d)", "GB ", standard_code)
        standard_code = re.sub(r"(?i)^QC/T(?=\d)", "QC/T ", standard_code)
        standard_code = re.sub(r"(?i)^QC(?=\d)", "QC ", standard_code)
        standard_code = standard_code.replace("-", "—")
        normalized_standard_matches.append(standard_code)

    primary_standard = None
    for candidate in normalized_standard_matches:
        if re.search(r"[-—]\d{4}$", candidate):
            primary_standard = candidate
            break
    if primary_standard is None and normalized_standard_matches:
        primary_standard = normalized_standard_matches[0]
    if primary_standard:
        results.append(("document_standard", "standard_code", {"value": primary_standard}))

    if not title_found:
        for line in lines:
            compact = re.sub(r"\s+", "", line)
            if not compact:
                continue
            if "国家标准" in compact:
                continue
            if re.search(r"^(ICS|CCS|GB/T|GB|ISO|IEC|\d{4}-\d{2}-\d{2})", compact):
                continue
            if "发布" in line or "实施" in line:
                continue
            if len(compact) < 8:
                continue
            if any(token in line for token in ("电动汽车", "charging", "系统", "部分", "逆变器", "电源")):
                results.append(("document_title", "title", {"value": re.sub(r"\s{2,}", " ", line).strip()}))
                title_found = True
                break

    replace_match = re.search(r"代替\s+([A-Z]{1,4}/?[A-Z]*\s*[\d.\-—]+)", text)
    if replace_match:
        results.append(("document_versioning", "replaces_standard", {"value": replace_match.group(1).strip()}))

    publish_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*发布", text)
    if publish_match:
        results.append(("document_lifecycle", "publication_date", {"value": publish_match.group(1).replace("—", "-")}))

    effective_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*实施", text)
    if effective_match:
        results.append(("document_lifecycle", "effective_date", {"value": effective_match.group(1).replace("—", "-")}))

    return results


def _extract_cover_metadata(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    text = _normalize_ocr_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    standard_matches = STANDARD_CODE_PATTERN.findall(joined)
    cleaned_standards: list[str] = []
    for match in standard_matches:
        standard_code = match.strip()
        standard_code = re.sub(r"(?i)^GBT", "GB/T", standard_code)
        standard_code = re.sub(r"(?i)^GB/T(?=\d)", "GB/T ", standard_code)
        standard_code = re.sub(r"(?i)^GB(?=\d)", "GB ", standard_code)
        standard_code = re.sub(r"(?i)^QC/T(?=\d)", "QC/T ", standard_code)
        standard_code = re.sub(r"(?i)^QC(?=\d)", "QC ", standard_code)
        standard_code = standard_code.replace("-", "—")
        cleaned_standards.append(standard_code)

    primary_standard = None
    for candidate in cleaned_standards:
        if re.search(r"[-—]\d{4}$", candidate):
            primary_standard = candidate
            break
    if primary_standard:
        results.append(("document_standard", "standard_code", {"value": primary_standard}))

    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if len(compact) < 8:
            continue
        if compact.startswith(("ICS", "CCS", "GB/T", "GB", "ISO", "IEC")):
            continue
        if "国家标准" in compact:
            continue
        if "发布" in line or "实施" in line:
            continue
        if any(token in line for token in ("电动汽车", "车载充电机", "charger", "charging", "系统", "部分", "逆变器", "电源")):
            results.append(("document_title", "title", {"value": re.sub(r"\s{2,}", " ", line).strip()}))
            break

    publish_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*发布", joined)
    if publish_match:
        results.append(("document_lifecycle", "publication_date", {"value": publish_match.group(1).replace("—", "-")}))

    effective_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*实施", joined)
    if effective_match:
        results.append(("document_lifecycle", "effective_date", {"value": effective_match.group(1).replace("—", "-")}))

    return results


def _extract_section_headings(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            if title and title not in seen:
                seen.add(title)
                results.append(
                    (
                        "section_heading",
                        "has_section",
                        {"title": title, "heading_level": level},
                    )
                )
            continue

        numbered = re.match(r"^(\d+(?:\.\d+){0,4})\s+(.+)$", line)
        if numbered:
            title = numbered.group(2).strip()
            if title and title not in seen:
                seen.add(title)
                results.append(
                    (
                        "section_heading",
                        "has_section",
                        {"title": title, "section_number": numbered.group(1), "heading_level": 0},
                    )
                )
    return results


def _extract_term_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    looks_like_term_page = (
        text.count("## ") >= 2 and text.count("#### ") >= 2 and re.search(r"####\s*\d+\.\d+\.\d+", text)
    )
    if (
        "术语和定义" not in text
        and "下列术语和定义适用于本文件" not in text
        and not looks_like_term_page
    ):
        return results

    seen: set[tuple[str, str]] = set()
    lines = text.splitlines()
    current_term: str | None = None
    current_definition_lines: list[str] = []

    def flush_term() -> None:
        nonlocal current_term, current_definition_lines
        if not current_term:
            current_definition_lines = []
            return

        term = _clean_text(current_term)
        definition = _clean_text("\n".join(current_definition_lines))
        if not term or not definition:
            current_term = None
            current_definition_lines = []
            return
        if len(term) > 80 or len(definition) < 12:
            current_term = None
            current_definition_lines = []
            return
        if term.lower() in {"前言", "引言", "目 次", "目次"}:
            current_term = None
            current_definition_lines = []
            return
        if re.match(r"^\d", term):
            current_term = None
            current_definition_lines = []
            return
        blocked_term_tokens = (
            "增加了",
            "更改了",
            "删除了",
            "见",
            "前言",
            "引言",
            "目 次",
            "目次",
            "范围",
            "规范性引用文件",
            "术语和定义",
        )
        if any(token in term for token in blocked_term_tokens):
            current_term = None
            current_definition_lines = []
            return
        if "：" in term or ":" in term:
            current_term = None
            current_definition_lines = []
            return
        if len(term.splitlines()) > 1:
            current_term = None
            current_definition_lines = []
            return
        if re.search(r"[，。；]$", term):
            current_term = None
            current_definition_lines = []
            return
        blocked_definition_tokens = (
            "增加了",
            "更改了",
            "删除了",
            "见2015年版",
            "见第",
            "本文件代替",
            "下列文件中的内容通过",
        )
        if any(token in definition for token in blocked_definition_tokens):
            current_term = None
            current_definition_lines = []
            return
        if "适用于本文件" in definition and len(definition) < 80:
            current_term = None
            current_definition_lines = []
            return
        if definition.count("GB/T") >= 4 and "是" not in definition and "指" not in definition:
            current_term = None
            current_definition_lines = []
            return
        if not any(token in definition for token in ("是", "指", "用于", "能够", "将", "利用", "通过", "为")):
            current_term = None
            current_definition_lines = []
            return
        key = (term, definition[:100])
        if key in seen:
            current_term = None
            current_definition_lines = []
            return
        seen.add(key)
        results.append(
            (
                "term_definition",
                "defines_term",
                {"term": term, "definition": definition},
            )
        )
        current_term = None
        current_definition_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("## "):
            flush_term()
            current_term = stripped[3:].strip()
            current_definition_lines = []
            continue

        if stripped.startswith(("### ", "#### ", "# ")):
            flush_term()
            current_term = None
            current_definition_lines = []
            continue

        if current_term is not None:
            current_definition_lines.append(line)

    flush_term()
    results.extend(_extract_markdown_bilingual_terms(text, seen))
    results.extend(_extract_numeric_term_definitions(text, seen))
    return results


def _extract_markdown_bilingual_terms(
    text: str,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    lines = [line.rstrip() for line in text.splitlines()]

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped.startswith("## "):
            continue
        term_line = stripped[3:].strip()
        if len(term_line) < 4:
            continue
        if not any(token in term_line for token in (":", "；", ";", " to ", "V2")):
            continue

        definition_lines: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                if definition_lines:
                    break
                cursor += 1
                continue
            if candidate.startswith("#") and not candidate.startswith(("### ", "#### ")):
                break
            if re.match(r"^\d+(?:\.\d+){1,4}\b", candidate):
                break
            definition_lines.append(candidate)
            cursor += 1

        definition = _clean_text("\n".join(definition_lines))
        term = _clean_text(term_line)
        if not term or not definition:
            continue
        if len(definition) < 12:
            continue
        if not any(token in definition for token in ("是", "指", "用于", "作为", "参与", "实现", "通过")):
            continue
        key = (term, definition[:100])
        if key in seen:
            continue
        seen.add(key)
        results.append(
            (
                "term_definition",
                "defines_term",
                {"term": term, "definition": definition},
            )
        )

    return results


def _extract_numeric_term_definitions(
    text: str,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    lines = [line.rstrip() for line in text.splitlines()]
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        if not re.match(r"^\d+\.\d+$", stripped):
            index += 1
            continue

        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            break

        term_line = lines[cursor].strip()
        if (
            term_line.startswith("#")
            or re.match(r"^\d+(?:\.\d+)+", term_line)
            or len(term_line) > 100
        ):
            index = cursor
            continue

        cursor += 1
        definition_lines: list[str] = []
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                if definition_lines:
                    break
                cursor += 1
                continue
            if candidate.startswith("#") or re.match(r"^\d+(?:\.\d+){1,4}\b", candidate):
                break
            definition_lines.append(candidate)
            cursor += 1

        definition = _clean_text("\n".join(definition_lines))
        term = _clean_text(_strip_bilingual_tail(term_line))
        if not term or not definition:
            index = cursor
            continue
        if len(term) > 80 or len(definition) < 12:
            index = cursor
            continue
        if not any(token in definition for token in ("是", "指", "用于", "能够", "将", "利用", "通过", "为")):
            index = cursor
            continue
        key = (term, definition[:100])
        if key in seen:
            index = cursor
            continue

        seen.add(key)
        results.append(
            (
                "term_definition",
                "defines_term",
                {"term": term, "definition": definition},
            )
        )
        index = cursor

    return results


def _strip_bilingual_tail(value: str) -> str:
    match = re.match(r"^(.*?)(?:\s+[A-Za-z][A-Za-z0-9\-()/ ]+)?$", value.strip())
    cleaned = match.group(1).strip() if match else value.strip()
    return re.sub(r"\s{2,}", " ", cleaned)


def _extract_abstract_concepts(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    normalized = _normalize_ocr_text(text)
    if "摘要" not in normalized and "Abstract" not in normalized:
        return results

    concept_patterns = [
        re.compile(
            r"(V2G)\s*\((Vehicle-to-Grid)\)\s*技术.*?作为一种(.+?)[。.]",
            re.S,
        ),
        re.compile(
            r"(Vehicle-to-Grid)\s*\((V2G)\)\s*technology.*?(facilitates.+?\.)",
            re.S | re.I,
        ),
    ]

    for pattern in concept_patterns:
        match = pattern.search(normalized)
        if not match:
            continue
        if match.group(1) == "V2G":
            term = "V2G"
            definition = _clean_text(f"Vehicle-to-Grid (V2G)技术作为一种{match.group(3)}。")
        else:
            term = "V2G"
            definition = _clean_text(match.group(0))
        results.append(
            (
                "concept_definition",
                "defines_concept",
                {"term": term, "definition": definition},
            )
        )
        break

    chinese_v2g_match = re.search(
        r"V2G\s*\((Vehicle-to-Grid)\)\s*技术作为一种创新的能源解决方案，通过实现电动车与电网之间的双向能量交换，(.+?)[。.]",
        normalized,
        re.S,
    )
    if chinese_v2g_match:
        definition = _clean_text(
            "V2G（Vehicle-to-Grid）技术是一种通过实现电动车与电网之间双向能量交换的创新能源解决方案，"
            + chinese_v2g_match.group(2)
            + "。"
        )
        results.insert(
            0,
            (
                "concept_definition",
                "defines_concept",
                {"term": "V2G", "definition": definition},
            ),
        )

    abstract_match = re.search(r"(?:摘\s*要|Abstract)\s*(.+)", normalized, re.S | re.I)
    if abstract_match:
        abstract_text = _clean_text(abstract_match.group(1))
        if len(abstract_text) > 80:
            results.append(
                (
                    "document_abstract",
                    "has_abstract",
                    {"value": abstract_text[:1200]},
                )
            )

    return results


def _extract_document_level_concepts(rows: list[object]) -> list[tuple[object, tuple[str, str, dict[str, object]]]]:
    if not rows:
        return []

    candidate_rows = [row for row in rows if row["page_no"] <= 2]
    combined_text = "\n".join(str(row["normalized_text"] or "") for row in candidate_rows)
    extracted = _extract_abstract_concepts(combined_text)
    if not extracted:
        return []

    anchor_row = candidate_rows[0]
    return [(anchor_row, item) for item in extracted]


def _extract_type_relations(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    normalized = _normalize_ocr_text(text)

    v2x_match = re.search(
        r"V2X.+?包括([^。]+)",
        normalized,
        re.I | re.S,
    )
    if not v2x_match:
        return results

    raw_items = re.split(r"[、,，；;]", v2x_match.group(1))
    cleaned_items: list[str] = []
    for item in raw_items:
        value = re.sub(r"等.*$", "", item).strip()
        if value and value not in cleaned_items:
            cleaned_items.append(value)

    for value in cleaned_items:
        results.append(
            (
                "comparison_relation",
                "includes_type",
                {"subject": "V2X", "item": value},
            )
        )

    return results


def _confidence(base: float, evidence_confidence: float) -> float:
    return round(max(0.1, min(1.0, (base + evidence_confidence) / 2)), 3)


def _knowledge_unit_fact_payloads(
    workspace_root: Path,
    doc_id: str,
) -> list[dict[str, object]]:
    cleaned_doc_ir_path = AppPaths.from_root(workspace_root).normalized / f"{doc_id}.cleaned_doc_ir.json"
    if not cleaned_doc_ir_path.exists():
        return []

    bundle = extract_knowledge_units(cleaned_doc_ir_path)
    save_knowledge_units(bundle, AppPaths.from_root(workspace_root).normalized / f"{doc_id}.knowledge_units.json")
    save_knowledge_units_jsonl(bundle, AppPaths.from_root(workspace_root).normalized / f"{doc_id}.kb.jsonl")

    payloads: list[dict[str, object]] = []
    for unit in bundle.units:
        if unit.type == "requirement":
            payloads.append(
                {
                    "fact_type": "requirement",
                    "predicate": "states_requirement",
                    "payload": {
                        "title": unit.title,
                        "content": unit.content,
                        "subject": unit.subject,
                        "condition": unit.condition,
                        "threshold": unit.threshold,
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.82,
                }
            )
            if unit.threshold:
                payloads.append(
                    {
                        "fact_type": "threshold",
                        "predicate": "has_threshold",
                        "payload": {
                            "title": unit.title,
                            "subject": unit.subject,
                            "value": unit.threshold,
                        },
                        "page_no": unit.page,
                        "base_confidence": 0.8,
                    }
                )
        elif unit.type == "table_requirement":
            payloads.append(
                {
                    "fact_type": "table_requirement",
                    "predicate": "has_table_requirement",
                    "payload": {
                        "title": unit.title,
                        "table_title": unit.table_title,
                        "headers": unit.headers,
                        "rows": unit.rows[:20] if unit.rows else [],
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.78,
                }
            )
    return payloads


def build_facts_for_document(workspace_root: Path, doc_id: str) -> FactsBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        rows = connection.execute(
            """
            SELECT evidence_id, page_no, confidence, risk_level, normalized_text
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()

        connection.execute(
            "DELETE FROM fact_evidence_map WHERE fact_id IN (SELECT fact_id FROM facts WHERE source_doc_id = ?)",
            (doc_id,),
        )
        connection.execute("DELETE FROM facts WHERE source_doc_id = ?", (doc_id,))

        exported: list[dict[str, object]] = []
        fact_types: dict[str, int] = {}
        seen_facts: set[str] = set()

        metadata_candidates: list[tuple[object, list[tuple[str, str, dict[str, object]]]]] = []
        page_payloads: list[tuple[object, list[tuple[str, str, dict[str, object]]]]] = []

        for row in rows:
            text = row["normalized_text"] or ""
            metadata_items: list[tuple[str, str, dict[str, object]]] = []
            if row["page_no"] == 1:
                metadata_items.extend(_extract_cover_metadata(text))
            if row["page_no"] <= 3:
                metadata_items.extend(_extract_doc_metadata(text))
                if metadata_items:
                    metadata_candidates.append((row, metadata_items))

            extracted: list[tuple[str, str, dict[str, object]]] = []
            extracted.extend(_extract_section_headings(text))
            extracted.extend(_extract_term_definitions(text))
            extracted.extend(_extract_type_relations(text))
            page_payloads.append((row, extracted))

        chosen_metadata: list[tuple[object, tuple[str, str, dict[str, object]]]] = []
        metadata_seen: set[tuple[str, str]] = set()
        for row, items in metadata_candidates:
            for fact_type, predicate, payload in items:
                key = (fact_type, predicate)
                if key in metadata_seen:
                    continue
                metadata_seen.add(key)
                chosen_metadata.append((row, (fact_type, predicate, payload)))

        for row, item in _extract_document_level_concepts(rows):
            fact_type, predicate, payload = item
            key = (fact_type, predicate)
            if key in metadata_seen:
                continue
            metadata_seen.add(key)
            chosen_metadata.append((row, item))

        for row, (fact_type, predicate, payload) in chosen_metadata:
            dedupe_key = json.dumps([fact_type, predicate, payload], ensure_ascii=False, sort_keys=True)
            if dedupe_key in seen_facts:
                continue
            seen_facts.add(dedupe_key)

            fact_id = next_prefixed_id(connection, "fact", "FACT")
            object_value = json.dumps(payload, ensure_ascii=False)
            confidence = _confidence(0.9, float(row["confidence"]))

            connection.execute(
                """
                INSERT INTO facts (
                    fact_id, fact_type, subject_entity_id, predicate, object_value,
                    object_entity_id, qualifiers_json, confidence, fact_status,
                    source_doc_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    fact_type,
                    None,
                    predicate,
                    object_value,
                    None,
                    json.dumps(
                        {
                            "page_no": row["page_no"],
                            "risk_level": row["risk_level"],
                        },
                        ensure_ascii=False,
                    ),
                    confidence,
                    "ready",
                    doc_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                VALUES (?, ?, ?)
                """,
                (fact_id, row["evidence_id"], "direct"),
            )

            fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
            exported.append(
                {
                    "fact_id": fact_id,
                    "fact_type": fact_type,
                    "predicate": predicate,
                    "object": payload,
                    "page_no": row["page_no"],
                    "evidence_id": row["evidence_id"],
                    "confidence": confidence,
                }
            )

        for row, extracted in page_payloads:
            for fact_type, predicate, payload in extracted:
                dedupe_key = json.dumps([fact_type, predicate, payload], ensure_ascii=False, sort_keys=True)
                if dedupe_key in seen_facts:
                    continue
                seen_facts.add(dedupe_key)

                fact_id = next_prefixed_id(connection, "fact", "FACT")
                object_value = json.dumps(payload, ensure_ascii=False)
                confidence = _confidence(
                    0.9 if fact_type not in {"term_definition", "concept_definition"} else 0.8,
                    float(row["confidence"]),
                )

                connection.execute(
                    """
                    INSERT INTO facts (
                        fact_id, fact_type, subject_entity_id, predicate, object_value,
                        object_entity_id, qualifiers_json, confidence, fact_status,
                        source_doc_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact_id,
                        fact_type,
                        None,
                        predicate,
                        object_value,
                        None,
                        json.dumps(
                            {
                                "page_no": row["page_no"],
                                "risk_level": row["risk_level"],
                            },
                            ensure_ascii=False,
                        ),
                        confidence,
                        "ready",
                        doc_id,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                    VALUES (?, ?, ?)
                    """,
                    (fact_id, row["evidence_id"], "direct"),
                )

                fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
                exported.append(
                    {
                        "fact_id": fact_id,
                        "fact_type": fact_type,
                        "predicate": predicate,
                        "object": payload,
                        "page_no": row["page_no"],
                        "evidence_id": row["evidence_id"],
                        "confidence": confidence,
                    }
                )

        export_path = paths.facts / f"{doc_id}.facts.json"
        row_by_page = {int(row["page_no"]): row for row in rows}
        for item in _knowledge_unit_fact_payloads(workspace_root, doc_id):
            row = row_by_page.get(int(item["page_no"])) or _nearest_evidence_row(rows, int(item["page_no"]))
            if row is None:
                continue
            dedupe_key = json.dumps(
                [item["fact_type"], item["predicate"], item["payload"]],
                ensure_ascii=False,
                sort_keys=True,
            )
            if dedupe_key in seen_facts:
                continue
            seen_facts.add(dedupe_key)

            fact_id = next_prefixed_id(connection, "fact", "FACT")
            object_value = json.dumps(item["payload"], ensure_ascii=False)
            confidence = _confidence(float(item["base_confidence"]), float(row["confidence"]))

            connection.execute(
                """
                INSERT INTO facts (
                    fact_id, fact_type, subject_entity_id, predicate, object_value,
                    object_entity_id, qualifiers_json, confidence, fact_status,
                    source_doc_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    item["fact_type"],
                    None,
                    item["predicate"],
                    object_value,
                    None,
                    json.dumps(
                        {
                            "page_no": row["page_no"],
                            "risk_level": row["risk_level"],
                        },
                        ensure_ascii=False,
                    ),
                    confidence,
                    "ready",
                    doc_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                VALUES (?, ?, ?)
                """,
                (fact_id, row["evidence_id"], "derived"),
            )
            fact_types[item["fact_type"]] = fact_types.get(item["fact_type"], 0) + 1
            exported.append(
                {
                    "fact_id": fact_id,
                    "fact_type": item["fact_type"],
                    "predicate": item["predicate"],
                    "object": item["payload"],
                    "page_no": row["page_no"],
                    "evidence_id": row["evidence_id"],
                    "confidence": confidence,
                }
            )

        export_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "fact_count": len(exported),
                    "fact_types": fact_types,
                    "items": exported,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        connection.commit()
        return FactsBuildResult(
            doc_id=doc_id,
            fact_count=len(exported),
            fact_types=fact_types,
            export_path=export_path,
        )
    finally:
        connection.close()


def _nearest_evidence_row(rows: list[object], page_no: int):
    if not rows:
        return None
    return min(rows, key=lambda row: abs(int(row["page_no"]) - page_no))
