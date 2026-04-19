from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id


@dataclass(frozen=True)
class RegisterResult:
    doc_id: str
    job_id: str | None
    deduplicated: bool
    stored_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _detect_source_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".text"}:
        return "text"
    if suffix in {".doc", ".docx"}:
        return "word"
    if suffix in {".xls", ".xlsx"}:
        return "excel"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return "image"
    return "file"


def register_document(workspace_root: Path, source_file: Path) -> RegisterResult:
    source_file = source_file.resolve()
    if not source_file.exists() or not source_file.is_file():
        raise FileNotFoundError(source_file)

    paths = AppPaths.from_root(workspace_root)
    db = connect(paths.db_file)
    sha256 = _sha256(source_file)
    mime_type, _ = mimetypes.guess_type(source_file.name)
    now = _utc_now()

    try:
        existing = db.execute(
            """
            SELECT doc_id, source_path
            FROM documents
            WHERE sha256 = ? AND is_active = 1
            ORDER BY ingest_time DESC
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()
        if existing is not None:
            return RegisterResult(
                doc_id=existing["doc_id"],
                job_id=None,
                deduplicated=True,
                stored_path=Path(existing["source_path"]),
            )

        doc_id = next_prefixed_id(db, "document", "DOC")
        job_id = next_prefixed_id(db, "job", "JOB")
        target_name = f"{doc_id}_{source_file.name}"
        stored_path = paths.raw / target_name
        shutil.copy2(source_file, stored_path)

        db.execute(
            """
            INSERT INTO documents (
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                source_file.name,
                _detect_source_type(source_file),
                mime_type,
                sha256,
                source_file.stat().st_size,
                None,
                None,
                None,
                str(stored_path),
                now,
                now,
                "queued",
                "pending",
                1,
            ),
        )

        db.execute(
            """
            INSERT INTO jobs (
                job_id, job_type, target_type, target_id, status, priority,
                payload_json, error_message, retry_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                "parse_document",
                "document",
                doc_id,
                "pending",
                5,
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "source_file": str(source_file),
                        "stored_path": str(stored_path),
                    },
                    ensure_ascii=False,
                ),
                None,
                0,
                now,
                now,
            ),
        )
        db.commit()
        return RegisterResult(
            doc_id=doc_id,
            job_id=job_id,
            deduplicated=False,
            stored_path=stored_path,
        )
    finally:
        db.close()
