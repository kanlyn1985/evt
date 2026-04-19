from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect


@dataclass(frozen=True)
class WikiBuildResult:
    doc_id: str
    page_count: int
    export_paths: list[Path]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "-", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "page"


def _load_payload(value: str) -> dict[str, object]:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def _term_is_publishable(name: str, description: str | None) -> bool:
    if not name or len(name) > 50:
        return False
    if description and len(description) > 800:
        return False
    if re.match(r"^\d", name):
        return False
    if ":" in name or "：" in name:
        return False
    if re.search(r"[，。；]$", name):
        return False
    blocked_tokens = (
        "增加了",
        "更改了",
        "删除了",
        "见",
        "目 次",
        "前言",
        "引言",
        "范围",
        "规范性引用文件",
        "术语和定义",
    )
    if any(token in name for token in blocked_tokens):
        return False
    if description:
        blocked_desc_tokens = ("增加了", "更改了", "删除了", "见2015年版", "下列文件中的内容通过")
        if any(token in description for token in blocked_desc_tokens):
            return False
    return True


def _build_document_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", ""]
    metadata_lines: list[str] = []
    sections: list[str] = []

    for row in facts:
        payload = _load_payload(row["object_value"])
        if row["fact_type"] == "document_title":
            metadata_lines.append(f"- 标题: {payload.get('value', '')}")
        elif row["fact_type"] == "document_standard":
            metadata_lines.append(f"- 标准号: {payload.get('value', '')}")
        elif row["fact_type"] == "document_versioning":
            metadata_lines.append(f"- 代替: {payload.get('value', '')}")
        elif row["fact_type"] == "document_lifecycle":
            label = "发布日期" if row["predicate"] == "publication_date" else "实施日期"
            metadata_lines.append(f"- {label}: {payload.get('value', '')}")
        elif row["fact_type"] == "section_heading":
            title = payload.get("title")
            if title:
                sections.append(str(title))

    lines.append("## 概览")
    lines.extend(metadata_lines or ["- 暂无结构化元信息"])
    lines.append("")
    if sections:
        lines.append("## 章节")
        lines.extend(f"- {title}" for title in sections[:50])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_standard_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", "", "## 关联事实"]
    for row in facts:
        subject_name = row["subject_name"] or row["source_doc_id"]
        lines.append(f"- {subject_name}: {row['predicate']}")
    lines.append("")
    return "\n".join(lines)


def _build_term_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", ""]
    definition_added = False
    for row in facts:
        if row["fact_type"] == "term_definition":
            payload = _load_payload(row["object_value"])
            definition = str(payload.get("definition", "")).strip()
            if definition:
                lines.append("## 定义")
                lines.append(definition)
                lines.append("")
                definition_added = True
                break
    if not definition_added and entity["description"]:
        lines.append("## 定义")
        lines.append(str(entity["description"]).strip())
        lines.append("")
    return "\n".join(lines)


def build_wiki_for_document(workspace_root: Path, doc_id: str) -> WikiBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        entity_rows = connection.execute(
            """
            SELECT DISTINCT e.entity_id, e.canonical_name, e.entity_type, e.description, e.source_confidence
            FROM entities e
            JOIN facts f
              ON f.subject_entity_id = e.entity_id OR f.object_entity_id = e.entity_id
            WHERE f.source_doc_id = ?
            ORDER BY e.entity_type, e.canonical_name
            """,
            (doc_id,),
        ).fetchall()

        export_paths: list[Path] = []

        for entity in entity_rows:
            if entity["entity_type"] == "term" and not _term_is_publishable(
                str(entity["canonical_name"]),
                str(entity["description"] or ""),
            ):
                continue

            fact_rows = connection.execute(
                """
                SELECT
                    f.fact_id,
                    f.fact_type,
                    f.predicate,
                    f.object_value,
                    f.source_doc_id,
                    s.canonical_name AS subject_name
                FROM facts f
                LEFT JOIN entities s ON f.subject_entity_id = s.entity_id
                WHERE f.source_doc_id = ?
                  AND (f.subject_entity_id = ? OR f.object_entity_id = ?)
                ORDER BY f.fact_id
                """,
                (doc_id, entity["entity_id"], entity["entity_id"]),
            ).fetchall()

            if entity["entity_type"] == "document":
                content = _build_document_page(entity, fact_rows)
                page_type = "document"
                subdir = "documents"
            elif entity["entity_type"] == "standard":
                content = _build_standard_page(entity, fact_rows)
                page_type = "standard"
                subdir = "standards"
            else:
                content = _build_term_page(entity, fact_rows)
                page_type = "term"
                subdir = "terms"

            target_dir = paths.wiki / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            slug = _slugify(str(entity["canonical_name"]))
            file_path = target_dir / f"{slug}.md"
            file_path.write_text(content, encoding="utf-8")
            export_paths.append(file_path)

            wiki_page_id = f"WPAGE-{entity['entity_id'].split('-', 1)[1]}"
            source_fact_ids = [row["fact_id"] for row in fact_rows]
            connection.execute(
                """
                INSERT INTO wiki_pages (
                    page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                    source_doc_ids_json, trust_status, file_path, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(page_id) DO UPDATE SET
                    page_type = excluded.page_type,
                    title = excluded.title,
                    slug = excluded.slug,
                    entity_id = excluded.entity_id,
                    source_fact_ids_json = excluded.source_fact_ids_json,
                    source_doc_ids_json = excluded.source_doc_ids_json,
                    trust_status = excluded.trust_status,
                    file_path = excluded.file_path,
                    updated_at = excluded.updated_at
                """,
                (
                    wiki_page_id,
                    page_type,
                    entity["canonical_name"],
                    slug,
                    entity["entity_id"],
                    json.dumps(source_fact_ids, ensure_ascii=False),
                    json.dumps([doc_id], ensure_ascii=False),
                    "reviewed" if entity["entity_type"] != "term" else "draft",
                    str(file_path),
                    now,
                ),
            )

        connection.commit()
        return WikiBuildResult(
            doc_id=doc_id,
            page_count=len(export_paths),
            export_paths=export_paths,
        )
    finally:
        connection.close()
