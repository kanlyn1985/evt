from __future__ import annotations

import html
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .answer_api import answer_query
from .config import AppPaths
from .db import connect
from .query_api import build_query_context


NETWORK_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
MIN_CASE_COUNT = 20
MAX_CASE_COUNT = 220


def generate_golden_tests_for_document(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    tests_dir = paths.root.parent / "tests" / "generated"
    tests_dir.mkdir(parents=True, exist_ok=True)

    try:
        document = connection.execute(
            """
            SELECT doc_id, source_filename, page_count
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document is None:
            raise ValueError(f"document not found: {doc_id}")

        facts = connection.execute(
            """
            SELECT fact_type, predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()
        evidence_rows = connection.execute(
            """
            SELECT page_no, normalized_text, confidence
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()
        wiki_rows = connection.execute(
            """
            SELECT page_type, title, slug
            FROM wiki_pages
            WHERE json_extract(source_doc_ids_json, '$[0]') = ?
            ORDER BY page_id
            """,
            (doc_id,),
        ).fetchall()

        target_case_count = _target_case_count(
            int(document["page_count"] or 0),
            len(facts),
            len(evidence_rows),
        )

        local_context = _build_local_context(document, facts, evidence_rows, wiki_rows)
        network_target = min(target_case_count, max(8, math.ceil(target_case_count * 0.6)))
        network_cases = _build_network_cases(local_context, network_target)
        network_candidate_count = len(network_cases)
        local_cases = _build_local_cases(local_context, target_case_count * 2)
        supplemental_cases = _build_local_cases(local_context, target_case_count * 3, extra_round=True)

        page_cases = _build_page_coverage_cases(local_context)
        candidate_pool = _dedupe_cases([*page_cases, *network_cases, *local_cases, *supplemental_cases])
        cases = _select_validated_cases(workspace_root, candidate_pool, target_case_count)
        if len(cases) < MIN_CASE_COUNT:
            extra_candidates = _dedupe_cases([*candidate_pool, *_build_last_resort_cases(local_context)])
            cases = _select_validated_cases(workspace_root, extra_candidates, MIN_CASE_COUNT)

        coverage = _page_coverage_summary(local_context, cases)

        json_path = tests_dir / f"{doc_id}.golden.json"
        json_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "source_filename": document["source_filename"],
                    "page_count": document["page_count"],
                    "target_case_count": target_case_count,
                    "network_candidate_count": network_candidate_count,
                    "network_case_count": sum(1 for item in cases if item.get("source") == "network"),
                    "local_case_count": sum(1 for item in cases if item.get("source") == "local"),
                    "page_coverage_count": coverage["page_coverage_count"],
                    "covered_pages": coverage["covered_pages"],
                    "uncovered_pages": coverage["uncovered_pages"],
                    "cases": cases,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        safe_doc_id = _safe_identifier(doc_id.lower())
        py_path = tests_dir / f"test_{safe_doc_id}_golden.py"
        py_path.write_text(_render_pytest_file(doc_id, cases), encoding="utf-8")

        return {
            "doc_id": doc_id,
            "source_filename": document["source_filename"],
            "page_count": document["page_count"],
            "target_case_count": target_case_count,
            "case_count": len(cases),
            "network_candidate_count": network_candidate_count,
            "network_case_count": sum(1 for item in cases if item.get("source") == "network"),
            "local_case_count": sum(1 for item in cases if item.get("source") == "local"),
            "page_coverage_count": coverage["page_coverage_count"],
            "covered_pages": coverage["covered_pages"],
            "uncovered_pages": coverage["uncovered_pages"],
            "json_path": str(json_path),
            "pytest_path": str(py_path),
            "cases": cases,
        }
    finally:
        connection.close()


def _target_case_count(page_count: int, fact_count: int, evidence_count: int) -> int:
    content_factor = min(20, max(0, fact_count // 8) + max(0, evidence_count // 6))
    proportional = max(MIN_CASE_COUNT, math.ceil(page_count * 0.55) + content_factor)
    return max(MIN_CASE_COUNT, min(MAX_CASE_COUNT, max(page_count, proportional)))


def _build_local_context(document, facts, evidence_rows, wiki_rows) -> dict[str, object]:
    fact_items = []
    for row in facts:
        fact_items.append(
            {
                "fact_type": row["fact_type"],
                "predicate": row["predicate"],
                "object_value": _safe_json(row["object_value"]),
                "qualifiers_json": _safe_json(row["qualifiers_json"]),
            }
        )

    evidence_items = [dict(row) for row in evidence_rows]
    wiki_items = [dict(row) for row in wiki_rows]

    standard_code = ""
    title = ""
    publication_date = ""
    effective_date = ""
    term_definitions: list[dict[str, str]] = []
    section_headings: list[dict[str, object]] = []

    for item in fact_items:
        payload = item["object_value"]
        if not isinstance(payload, dict):
            continue
        if item["fact_type"] == "document_standard" and not standard_code:
            standard_code = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_title" and not title:
            title = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "publication_date" and not publication_date:
            publication_date = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "effective_date" and not effective_date:
            effective_date = str(payload.get("value", "")).strip()
        elif item["fact_type"] in {"term_definition", "concept_definition"}:
            term = str(payload.get("term", "")).strip()
            definition = str(payload.get("definition", "")).strip()
            if term and definition:
                term_definitions.append({"term": term, "definition": definition})
        elif item["fact_type"] == "section_heading":
            title_value = str(payload.get("title", "")).strip()
            if title_value:
                section_headings.append(
                    {
                        "title": title_value,
                        "page_no": int(item["qualifiers_json"].get("page_no", 0))
                        if isinstance(item["qualifiers_json"], dict)
                        else 0,
                    }
                )

    normalized_texts = [
        document["source_filename"],
        standard_code,
        title,
        publication_date,
        effective_date,
        *[json.dumps(item["object_value"], ensure_ascii=False) for item in fact_items],
        *[str(item["normalized_text"]) for item in evidence_items],
        *[str(item["title"]) for item in wiki_items],
    ]
    local_corpus = "\n".join(part for part in normalized_texts if part)

    return {
        "doc_id": document["doc_id"],
        "source_filename": document["source_filename"],
        "page_count": int(document["page_count"] or 0),
        "standard_code": standard_code,
        "title": title,
        "publication_date": publication_date,
        "effective_date": effective_date,
        "facts": fact_items,
        "evidence": evidence_items,
        "wiki": wiki_items,
        "term_definitions": term_definitions,
        "section_headings": section_headings,
        "local_corpus": local_corpus,
        "pages_with_evidence": sorted({int(item["page_no"]) for item in evidence_items if int(item.get("page_no") or 0) > 0}),
    }


def _build_network_cases(local_context: dict[str, object], target_count: int) -> list[dict[str, object]]:
    if target_count <= 0:
        return []

    search_queries = _build_search_queries(local_context)
    cases: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    page_fetch_budget = 6

    for query in search_queries:
        for hit in _search_duckduckgo(query):
            if page_fetch_budget <= 0:
                return _dedupe_cases(cases)[:target_count]
            if hit["url"] in seen_urls:
                continue
            seen_urls.add(hit["url"])
            page_fetch_budget -= 1

            source_text = "\n".join(
                part for part in [hit["title"], hit["snippet"], _fetch_page_text(hit["url"])] if part
            )
            if not source_text.strip():
                continue

            extracted = _extract_network_metadata(source_text)
            candidates = _network_cases_from_metadata(local_context, extracted, hit["url"])
            for case in candidates:
                cases.append(case)
                if len(_dedupe_cases(cases)) >= target_count:
                    return _dedupe_cases(cases)[:target_count]

    return _dedupe_cases(cases)[:target_count]


def _build_search_queries(local_context: dict[str, object]) -> list[str]:
    filename_stem = Path(str(local_context["source_filename"])).stem
    standard_code = str(local_context.get("standard_code", "")).replace("—", "-")
    title = str(local_context.get("title", ""))
    queries = [
        f"{standard_code} {title}".strip(),
        f"{standard_code} {filename_stem}".strip(),
        filename_stem,
        standard_code,
        title,
    ]
    deduped: list[str] = []
    for item in queries:
        cleaned = re.sub(r"\s+", " ", item).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:4]


def _search_duckduckgo(query: str) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": NETWORK_USER_AGENT},
            timeout=8.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    hits: list[dict[str, str]] = []
    title_matches = list(
        re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            response.text,
            re.S,
        )
    )
    snippet_matches = list(
        re.finditer(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>',
            response.text,
            re.S,
        )
    )

    for index, match in enumerate(title_matches[:8]):
        raw_url = html.unescape(match.group(1))
        title = _strip_html(html.unescape(match.group(2)))
        snippet = ""
        if index < len(snippet_matches):
            body = snippet_matches[index].group(1) or snippet_matches[index].group(2) or ""
            snippet = _strip_html(html.unescape(body))
        url = _resolve_duckduckgo_url(raw_url)
        if url:
            hits.append({"title": title, "snippet": snippet, "url": url})
    return hits


def _resolve_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urlparse(raw_url)
    if "duckduckgo.com" not in parsed.netloc:
        return raw_url
    uddg = parse_qs(parsed.query).get("uddg")
    if not uddg:
        return ""
    return unquote(uddg[0])


def _fetch_page_text(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": NETWORK_USER_AGENT},
            timeout=6.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return ""

    text = _strip_html(response.text)
    return re.sub(r"\s+", " ", text).strip()[:5000]


def _extract_network_metadata(text: str) -> dict[str, list[str]]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    metadata: dict[str, list[str]] = {
        "standard_codes": _unique_matches(
            r"(?:GB/T|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[-—]\d{2,4})?",
            cleaned,
        ),
        "dates": _unique_matches(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", cleaned),
        "status": _unique_matches(r"(?:Status[:：]?\s*[A-Za-z]+|现行|有效|Valid)", cleaned, flags=re.I),
        "titles": _extract_candidate_titles(cleaned),
        "scope": _extract_scope_sentences(cleaned),
        "organizations": _extract_organizations(cleaned),
    }
    return metadata


def _network_cases_from_metadata(
    local_context: dict[str, object],
    metadata: dict[str, list[str]],
    source_url: str,
) -> list[dict[str, str]]:
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    publication_date = str(local_context.get("publication_date", "")).strip()
    effective_date = str(local_context.get("effective_date", "")).strip()

    cases: list[dict[str, str]] = []
    if standard_code:
        cases.append(
            _case(
                "network_standard",
                f"{standard_code} 的标准号是什么？",
                standard_code,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if publication_date:
        cases.append(
            _case(
                "network_publication_date",
                f"{standard_code or title} 的发布日期是什么？",
                publication_date,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if effective_date:
        cases.append(
            _case(
                "network_effective_date",
                f"{standard_code or title} 的实施日期是什么？",
                effective_date,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if title:
        cases.append(
            _case(
                "network_title",
                f"{standard_code or title} 的中文名称是什么？",
                title,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )

    for value in metadata.get("titles", [])[:3]:
        if value != title:
            cases.append(
                _case(
                    "network_title_variant",
                    f"{standard_code or title} 的名称或公开标题是什么？",
                    value,
                    source="network",
                    assert_mode="rich_answer",
                    source_url=source_url,
                )
            )

    for value in metadata.get("organizations", [])[:4]:
        cases.append(
            _case(
                "network_org",
                f"{standard_code or title} 的发布或起草信息中是否包含 {value}？",
                value,
                source="network",
                assert_mode="context_contains",
                source_url=source_url,
            )
        )

    for value in metadata.get("scope", [])[:4]:
        cases.append(
            _case(
                "network_scope",
                f"{standard_code or title} 适用于什么对象或范围？",
                value,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )

    return cases


def _build_local_cases(
    local_context: dict[str, object],
    target_count: int,
    extra_round: bool = False,
) -> list[dict[str, str]]:
    if target_count <= 0:
        return []

    cases: list[dict[str, str]] = []
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    publication_date = str(local_context.get("publication_date", "")).strip()
    effective_date = str(local_context.get("effective_date", "")).strip()

    if standard_code:
        for query in [
            f"{standard_code} 的标准号和实施日期是什么？",
            f"{standard_code} 对应的标准编号是什么？",
            f"{standard_code} 的现行标准号是什么？",
        ]:
            cases.append(_case("standard", query, standard_code, source="local", assert_mode="rich_answer"))

    if publication_date:
        for query in [
            f"{standard_code or title} 的发布日期是什么？",
            f"{standard_code or title} 是哪一天发布的？",
        ]:
            cases.append(_case("publication_date", query, publication_date, source="local", assert_mode="rich_answer"))

    if effective_date:
        for query in [
            f"{standard_code or title} 的实施日期是什么？",
            f"{standard_code or title} 从哪一天开始实施？",
        ]:
            cases.append(_case("effective_date", query, effective_date, source="local", assert_mode="rich_answer"))

    if title:
        cases.append(_case("title", f"{standard_code or title} 这份文档的标题是什么？", title, source="local", assert_mode="rich_answer"))

    for item in list(local_context.get("term_definitions", []))[:8]:
        term = str(item["term"]).strip()
        definition = str(item["definition"]).strip()
        if not term or not definition:
            continue
        definition_query_prefix = f"在{standard_code}中，" if standard_code else ""
        cases.append(
            _case(
                "definition",
                f"{definition_query_prefix}什么是{term}？",
                term,
                source="local",
                assert_mode="rich_answer",
            )
        )
        cases.append(
            _case(
                "definition_detail",
                f"{definition_query_prefix}{term} 的定义是什么？",
                _definition_anchor(definition),
                source="local",
                assert_mode="rich_answer",
            )
        )

    sampled_headings = _sample_headings(list(local_context.get("section_headings", [])), 4 if not extra_round else 6)
    for heading in sampled_headings:
        title_value = str(heading["title"]).strip()
        if not title_value:
            continue
        cases.append(
            _case(
                "section",
                f"在{standard_code or '该文档'}中，是否包含“{title_value}”这一章节？",
                title_value,
                source="local",
                assert_mode="context_contains",
                page_no=int(heading.get("page_no") or 0),
            )
        )

    evidence_cases = _cases_from_evidence(list(local_context.get("evidence", [])), extra_round=extra_round)
    cases.extend(evidence_cases)

    return _dedupe_cases(cases)[:target_count]


def _cases_from_evidence(evidence_items: list[dict[str, object]], extra_round: bool = False) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    sentence_budget = 10 if not extra_round else 18
    sentences: list[str] = []

    for item in evidence_items:
        text = str(item.get("normalized_text", "")).strip()
        if not text:
            continue
        for sentence in _extract_candidate_sentences(text):
            if sentence not in sentences:
                sentences.append(sentence)
            if len(sentences) >= sentence_budget:
                break
        if len(sentences) >= sentence_budget:
            break

    for sentence in sentences:
        if "适用于" in sentence:
            query = "本标准适用于什么对象或范围？"
        elif "规定了" in sentence:
            query = "本标准规定了哪些内容？"
        elif "发布" in sentence and re.search(r"\d{4}-\d{2}-\d{2}", sentence):
            query = "文档里给出的发布日期是什么？"
        elif "实施" in sentence and re.search(r"\d{4}-\d{2}-\d{2}", sentence):
            query = "文档里给出的实施日期是什么？"
        else:
            query = f"文档中关于“{_query_anchor(sentence)}”是怎么表述的？"
        cases.append(
            _case(
                "evidence",
                query,
                _definition_anchor(sentence),
                source="local",
                assert_mode="rich_answer",
                page_no=int(item.get("page_no") or 0),
            )
        )

    return cases


def _build_page_coverage_cases(local_context: dict[str, object]) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    per_page_seen: set[int] = set()

    for evidence_item in list(local_context.get("evidence", [])):
        page_no = int(evidence_item.get("page_no") or 0)
        if page_no <= 0 or page_no in per_page_seen:
            continue
        text = str(evidence_item.get("normalized_text", "")).strip()
        sentence = _select_page_anchor_sentence(text) or _select_page_anchor_fragment(text)
        if not sentence:
            continue
        per_page_seen.add(page_no)
        anchor = _definition_anchor(sentence, max_chars=38)
        query = f"第{page_no}页 {anchor}"
        cases.append(
            _case(
                "page_coverage",
                query,
                anchor,
                source="local",
                assert_mode="context_contains",
                page_no=page_no,
            )
        )

    return cases


def _build_last_resort_cases(local_context: dict[str, object]) -> list[dict[str, str]]:
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    cases: list[dict[str, str]] = []
    for heading in list(local_context.get("section_headings", [])):
        title_value = str(heading.get("title", "")).strip()
        if not title_value:
            continue
        query = f"{standard_code or title} {title_value}"
        cases.append(
            _case(
                "keyword_section",
                query,
                title_value,
                source="local",
                assert_mode="context_contains",
                page_no=int(heading.get("page_no") or 0),
            )
        )
    for term_item in list(local_context.get("term_definitions", [])):
        term = str(term_item.get("term", "")).strip()
        if term:
            query = f"{standard_code or title} {term}"
            cases.append(_case("keyword_term", query, term, source="local", assert_mode="context_contains"))
    for wiki_item in list(local_context.get("wiki", [])):
        wiki_title = str(wiki_item.get("title", "")).strip()
        if wiki_title:
            cases.append(
                _case(
                    "keyword_wiki",
                    wiki_title,
                    wiki_title,
                    source="local",
                    assert_mode="context_contains",
                )
            )
    evidence_budget = 24
    for evidence_item in list(local_context.get("evidence", [])):
        text = str(evidence_item.get("normalized_text", "")).strip()
        if not text:
            continue
        for sentence in _extract_candidate_sentences(text):
            anchor = _definition_anchor(sentence, max_chars=28)
            if len(anchor) < 10:
                continue
            cases.append(
                _case(
                    "keyword_evidence",
                    anchor,
                    anchor,
                    source="local",
                    assert_mode="context_contains",
                    page_no=int(evidence_item.get("page_no") or 0),
                )
            )
            evidence_budget -= 1
            if evidence_budget <= 0:
                break
        if evidence_budget <= 0:
            break
    return cases


def _sample_headings(headings: list[dict[str, object]], budget: int) -> list[dict[str, object]]:
    if len(headings) <= budget:
        return headings
    step = max(1, len(headings) // budget)
    sampled = [headings[index] for index in range(0, len(headings), step)]
    return sampled[:budget]


def _case(
    kind: str,
    query: str,
    must_include: str,
    *,
    source: str,
    assert_mode: str,
    page_no: int | None = None,
    source_url: str | None = None,
) -> dict[str, str]:
    payload = {
        "kind": kind,
        "query": re.sub(r"\s+", " ", query).strip(),
        "must_include": re.sub(r"\s+", " ", must_include).strip(),
        "source": source,
        "assert_mode": assert_mode,
    }
    if page_no:
        payload["page_no"] = int(page_no)
    if source_url:
        payload["source_url"] = source_url
    return payload


def _dedupe_cases(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for case in cases:
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in seen or not case.get("must_include"):
            continue
        seen.add(key)
        deduped.append(case)
    return deduped


def _contains_locally(local_corpus: str, expected: str) -> bool:
    if not expected:
        return False
    return _normalize_compare(expected) in _normalize_compare(local_corpus)


def _extract_candidate_titles(text: str) -> list[str]:
    titles: list[str] = []
    for pattern in [
        r"(Automotive DC-AC power inverter)",
        r"(汽车电源逆变器)",
        r"(电动汽车用传导式车载充电机)",
        r"(电动汽车传导充电系统[^。；]{0,60})",
    ]:
        titles.extend(_unique_matches(pattern, text, flags=re.I))
    return titles[:6]


def _extract_scope_sentences(text: str) -> list[str]:
    scopes: list[str] = []
    for match in re.finditer(r"((?:本标准|本文件).{0,80}?(?:规定了|适用于).{0,120}[。；])", text):
        scopes.append(_definition_anchor(match.group(1)))
    for match in re.finditer(r"((?:This standard|This document).{0,140}?(?:specifies|applies to).{0,180}\.)", text, re.I):
        scopes.append(_definition_anchor(match.group(1)))
    return _unique_values(scopes)[:6]


def _extract_organizations(text: str) -> list[str]:
    organizations: list[str] = []
    for pattern in [
        r"(中华人民共和国工业和信息化部)",
        r"(全国汽车标准化技术委员会[^，。；]{0,40})",
        r"(上海汽车集团股份有限公司技术中心)",
        r"(长沙汽车电器研究所)",
    ]:
        organizations.extend(_unique_matches(pattern, text))
    return _unique_values(organizations)[:6]


def _unique_matches(pattern: str, text: str, *, flags: int = 0) -> list[str]:
    return _unique_values(match.group(0).strip() for match in re.finditer(pattern, text, flags))


def _unique_values(values) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _extract_candidate_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[。；.!?])\s+", cleaned)
    sentences: list[str] = []
    for part in parts:
        segment = part.strip()
        if len(segment) < 16:
            continue
        if "<table" in segment.lower():
            continue
        if segment not in sentences:
            sentences.append(segment)
    return sentences[:6]


def _select_page_anchor_sentence(text: str) -> str:
    sentences = _extract_candidate_sentences(text)
    ranked = sorted(sentences, key=_page_sentence_score, reverse=True)
    return ranked[0] if ranked else ""


def _select_page_anchor_fragment(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", _strip_html(text)).strip()
    if not cleaned:
        return ""
    for pattern in [
        r"(QC/T\s*[\d.]+[—-]\d{4})",
        r"(GB/T\s*[\d.]+[—-]\d{4})",
        r"(第\s*\d+\s*部分[^，。；]{0,18})",
        r"([一二三四五六七八九十\d]+\s*[范围要求试验方法检验规则术语定义保护功能效率电压功率]{1,8}[^，。；]{0,18})",
    ]:
        match = re.search(pattern, cleaned, re.I)
        if match:
            return match.group(1).strip()
    if len(cleaned) <= 28:
        return cleaned
    return cleaned[:28].rstrip(" ，,;；。") + "..."


def _page_sentence_score(sentence: str) -> tuple[int, int]:
    penalty = 1 if any(token in sentence for token in ("目次", "目 次", "前言", "目录", "chapter", "contents")) else 0
    signal = sum(1 for token in ("适用于", "规定", "要求", "试验", "定义", "保护", "输出", "电压", "功率", "效率") if token in sentence)
    return (signal - penalty, len(sentence))


def _definition_anchor(text: str, max_chars: int = 42) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip(" ，,;；。") + "..."


def _query_anchor(text: str, max_chars: int = 18) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip(" ，,;；。") + "..."


def _strip_html(text: str) -> str:
    stripped = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    stripped = re.sub(r"<style.*?</style>", " ", stripped, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return html.unescape(stripped)


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _normalize_compare(value: str) -> str:
    text = value.lower()
    text = text.replace("—", "-").replace("／", "/")
    text = re.sub(r"\s+", "", text)
    return text


def _render_pytest_file(doc_id: str, cases: list[dict[str, str]]) -> str:
    safe_doc_id = _safe_identifier(doc_id.lower())
    lines = [
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        "from enterprise_agent_kb.answer_api import answer_query",
        "from enterprise_agent_kb.query_api import build_query_context",
        "",
        'WORKSPACE = Path("knowledge_base")',
        "",
        "",
        "def _normalize(value: str) -> str:",
        '    text = value.lower().replace("—", "-").replace("／", "/")',
        '    return "".join(text.split())',
        "",
        "",
        "def _assert_case(case: dict[str, str]) -> None:",
        '    expected = _normalize(case["must_include"])',
        '    if case.get("assert_mode") == "context_contains":',
        '        context = build_query_context(WORKSPACE, case["query"], limit=8)',
        '        blob = json.dumps(context, ensure_ascii=False)',
        '    else:',
        '        answer = answer_query(WORKSPACE, case["query"], limit=8)',
        '        blob = "\\n".join(',
        '            [',
        '                str(answer.get("direct_answer", "")),',
        '                *[str(item) for item in answer.get("summary", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],',
        '            ]',
        '        )',
        '    assert expected in _normalize(blob)',
        "",
    ]
    for index, case in enumerate(cases, start=1):
        lines.extend(
            [
                "@pytest.mark.integration",
                "@pytest.mark.benchmark",
                f"def test_{safe_doc_id}_golden_{index}() -> None:",
                f"    case = {json.dumps(case, ensure_ascii=False)!r}",
                "    _assert_case(json.loads(case))",
                "",
            ]
        )
    return "\n".join(lines)


def _select_validated_cases(
    workspace_root: Path,
    candidate_pool: list[dict[str, str]],
    target_count: int,
) -> list[dict[str, str]]:
    prioritized = _prioritize_cases(candidate_pool)
    validated: list[dict[str, str]] = []
    selected_keys: set[tuple[str, str, str]] = set()

    network_candidates = [case for case in prioritized if case.get("source") == "network"]
    page_candidates = [case for case in prioritized if case.get("kind") == "page_coverage"]
    other_candidates = [
        case for case in prioritized
        if case.get("source") != "network" and case.get("kind") != "page_coverage"
    ]

    network_quota = 0
    if network_candidates:
        network_quota = max(1, min(6, math.ceil(target_count * 0.2)))

    validated.extend(_validate_into(workspace_root, network_candidates, network_quota, selected_keys))
    validated.extend(_validate_page_coverage(workspace_root, page_candidates, target_count - len(validated), selected_keys))
    if len(validated) < target_count:
        validated.extend(_validate_into(workspace_root, other_candidates, target_count - len(validated), selected_keys))
    if len(validated) < target_count:
        validated.extend(_validate_into(workspace_root, network_candidates, target_count - len(validated), selected_keys))

    return validated[:target_count]


def _validate_into(
    workspace_root: Path,
    cases: list[dict[str, str]],
    limit: int,
    selected_keys: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    if limit <= 0:
        return accepted
    for case in cases:
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in selected_keys:
            continue
        if _validate_case(workspace_root, case):
            accepted.append(case)
            selected_keys.add(key)
        if len(accepted) >= limit:
            break
    return accepted


def _validate_page_coverage(
    workspace_root: Path,
    cases: list[dict[str, str]],
    limit: int,
    selected_keys: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    covered_pages: set[int] = set()
    if limit <= 0:
        return accepted
    for case in cases:
        page_no = int(case.get("page_no") or 0)
        if page_no in covered_pages:
            continue
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in selected_keys:
            continue
        if _validate_case(workspace_root, case):
            accepted.append(case)
            covered_pages.add(page_no)
            selected_keys.add(key)
        if len(accepted) >= limit:
            break
    return accepted


def _prioritize_cases(candidate_pool: list[dict[str, str]]) -> list[dict[str, str]]:
    prioritized: list[dict[str, str]] = []
    used_pages: set[int] = set()
    remainder: list[dict[str, str]] = []

    for case in candidate_pool:
        page_no = int(case.get("page_no") or 0)
        if case.get("kind") == "page_coverage" and page_no > 0 and page_no not in used_pages:
            prioritized.append(case)
            used_pages.add(page_no)
        else:
            remainder.append(case)

    remainder.sort(key=_case_priority)
    for case in remainder:
        page_no = int(case.get("page_no") or 0)
        if page_no > 0 and page_no not in used_pages:
            prioritized.append(case)
            used_pages.add(page_no)
        else:
            prioritized.append(case)
    return prioritized


def _case_priority(case: dict[str, str]) -> tuple[int, int]:
    kind = str(case.get("kind", ""))
    page_no = int(case.get("page_no") or 0)
    if kind == "page_coverage":
        rank = 0
    elif kind in {"evidence", "definition", "definition_detail", "network_scope"}:
        rank = 1
    elif kind in {"standard", "publication_date", "effective_date", "network_standard", "network_publication_date", "network_effective_date"}:
        rank = 2
    elif kind in {"section", "keyword_evidence", "keyword_term"}:
        rank = 3
    else:
        rank = 5
    return (rank, page_no or 10_000)


def _validate_case(workspace_root: Path, case: dict[str, str]) -> bool:
    expected = _normalize_compare(case.get("must_include", ""))
    if not expected:
        return False

    try:
        if case.get("assert_mode") == "context_contains":
            context = build_query_context(workspace_root, case["query"], limit=8)
            blob = json.dumps(context, ensure_ascii=False)
        else:
            answer = answer_query(workspace_root, case["query"], limit=8)
            blob = "\n".join(
                [
                    str(answer.get("direct_answer", "")),
                    *[str(item) for item in answer.get("summary", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],
                ]
            )
    except Exception:
        return False

    return expected in _normalize_compare(blob)


def _page_coverage_summary(local_context: dict[str, object], cases: list[dict[str, str]]) -> dict[str, object]:
    all_pages = list(local_context.get("pages_with_evidence", []))
    covered_pages = sorted({int(item.get("page_no") or 0) for item in cases if int(item.get("page_no") or 0) > 0})
    uncovered_pages = [page for page in all_pages if page not in covered_pages]
    return {
        "page_coverage_count": len(covered_pages),
        "covered_pages": covered_pages,
        "uncovered_pages": uncovered_pages,
    }


def run_golden_tests_for_document(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    safe_doc_id = _safe_identifier(doc_id.lower())
    py_path = tests_dir / f"test_{safe_doc_id}_golden.py"
    if not py_path.exists():
        generate_golden_tests_for_document(workspace_root, doc_id)
    if not py_path.exists():
        raise ValueError(f"generated pytest file missing for {doc_id}")

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "integration or benchmark",
        str(py_path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(paths.root.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    passed, failed = _parse_pytest_counts(combined)
    return {
        "doc_id": doc_id,
        "pytest_path": str(py_path),
        "command": " ".join(command),
        "return_code": completed.returncode,
        "passed": passed,
        "failed": failed,
        "success": completed.returncode == 0,
        "output": combined[-12000:],
    }


def _parse_pytest_counts(output: str) -> tuple[int, int]:
    passed = 0
    failed = 0
    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    return passed, failed


def _safe_identifier(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "generated"
