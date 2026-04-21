from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id


@dataclass(frozen=True)
class EntitiesBuildResult:
    doc_id: str
    entity_count: int
    entity_types: dict[str, int]
    export_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _extract_payload(row) -> dict[str, object]:
    try:
        return json.loads(row["object_value"] or "{}")
    except json.JSONDecodeError:
        return {}


def _find_existing_entity_id(connection, canonical_name: str, entity_type: str) -> str | None:
    row = connection.execute(
        """
        SELECT entity_id
        FROM entities
        WHERE canonical_name = ? AND entity_type = ?
        LIMIT 1
        """,
        (canonical_name, entity_type),
    ).fetchone()
    return row["entity_id"] if row else None


def _ensure_entity(
    connection,
    canonical_name: str,
    entity_type: str,
    description: str | None,
    confidence: float,
    now: str,
) -> str:
    existing_id = _find_existing_entity_id(connection, canonical_name, entity_type)
    if existing_id:
        connection.execute(
            """
            UPDATE entities
            SET description = COALESCE(description, ?),
                source_confidence = MAX(COALESCE(source_confidence, 0), ?),
                updated_at = ?
            WHERE entity_id = ?
            """,
            (description, confidence, now, existing_id),
        )
        return existing_id

    entity_id = next_prefixed_id(connection, "entity", "ENT")
    connection.execute(
        """
        INSERT INTO entities (
            entity_id, canonical_name, entity_type, alias_json, description,
            source_confidence, entity_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_id,
            canonical_name,
            entity_type,
            json.dumps([], ensure_ascii=False),
            description,
            confidence,
            "ready",
            now,
            now,
        ),
    )
    return entity_id


def build_entities_for_document(workspace_root: Path, doc_id: str) -> EntitiesBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        doc_row = connection.execute(
            """
            SELECT source_filename
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if doc_row is None:
            raise ValueError(f"document not found: {doc_id}")

        fact_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()

        doc_entity_name = f"{doc_id}:{doc_row['source_filename']}"
        doc_entity_id = _ensure_entity(
            connection,
            canonical_name=doc_entity_name,
            entity_type="document",
            description=f"Source document {doc_row['source_filename']}",
            confidence=1.0,
            now=now,
        )

        entity_ids_for_export: dict[str, tuple[str, str, str | None, float]] = {
            doc_entity_id: (doc_entity_name, "document", f"Source document {doc_row['source_filename']}", 1.0)
        }

        for row in fact_rows:
            payload = _extract_payload(row)
            fact_id = row["fact_id"]
            confidence = float(row["confidence"] or 0.8)

            connection.execute(
                "UPDATE facts SET subject_entity_id = ? WHERE fact_id = ?",
                (doc_entity_id, fact_id),
            )

            if row["fact_type"] == "document_standard":
                value = str(payload.get("value", "")).strip()
                if value:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=value,
                        entity_type="standard",
                        description="Standard code referenced by document",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (value, "standard", "Standard code referenced by document", confidence)

            elif row["fact_type"] == "document_versioning":
                value = str(payload.get("value", "")).strip()
                if value:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=value,
                        entity_type="standard",
                        description="Superseded or referenced standard",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (value, "standard", "Superseded or referenced standard", confidence)

            elif row["fact_type"] in {"term_definition", "concept_definition"}:
                term = str(payload.get("term", "")).strip()
                definition = str(payload.get("definition", "")).strip()
                if term:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=term,
                        entity_type="term",
                        description=definition or None,
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        """
                        UPDATE facts
                        SET subject_entity_id = ?, object_entity_id = NULL
                        WHERE fact_id = ?
                        """,
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (term, "term", definition or None, confidence)

            elif row["fact_type"] in {"process_fact", "transition_fact"}:
                process_name = str(
                    payload.get("table_title")
                    or payload.get("title")
                    or payload.get("process_name")
                    or ""
                ).strip()
                if process_name:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=process_name,
                        entity_type="process",
                        description="Process/timing knowledge object",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (process_name, "process", "Process/timing knowledge object", confidence)

            elif row["fact_type"] == "table_requirement":
                table_title = str(payload.get("table_title") or payload.get("title") or "").strip()
                if table_title and "参数" in table_title:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=table_title,
                        entity_type="parameter_group",
                        description="Parameter group derived from table",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (table_title, "parameter_group", "Parameter group derived from table", confidence)

            elif row["fact_type"] in {"requirement", "threshold"}:
                topic = str(payload.get("topic") or payload.get("subject") or "").strip()
                scope_type = str(payload.get("scope_type") or "").strip()
                if topic and scope_type not in {"index", "preface", "overview"}:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=topic,
                        entity_type="constraint_topic",
                        description=f"Constraint topic {topic}",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (topic, "constraint_topic", f"Constraint topic {topic}", confidence)

            elif row["fact_type"] == "comparison_relation":
                subject = str(payload.get("subject") or "").strip()
                if subject:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=subject,
                        entity_type="comparison_topic",
                        description=f"Comparison topic {subject}",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (subject, "comparison_topic", f"Comparison topic {subject}", confidence)

        export_items = [
            {
                "entity_id": entity_id,
                "canonical_name": values[0],
                "entity_type": values[1],
                "description": values[2],
                "source_confidence": values[3],
            }
            for entity_id, values in sorted(entity_ids_for_export.items())
        ]

        entity_types: dict[str, int] = {}
        for item in export_items:
            entity_types[item["entity_type"]] = entity_types.get(item["entity_type"], 0) + 1

        export_path = paths.facts / f"{doc_id}.entities.json"
        export_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "entity_count": len(export_items),
                    "entity_types": entity_types,
                    "items": export_items,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        connection.commit()
        return EntitiesBuildResult(
            doc_id=doc_id,
            entity_count=len(export_items),
            entity_types=entity_types,
            export_path=export_path,
        )
    finally:
        connection.close()
