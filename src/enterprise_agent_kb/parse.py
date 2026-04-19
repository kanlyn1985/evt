from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import fitz
import httpx

from .config import AppPaths
from .db import connect
from .doc_ir import build_doc_ir, save_doc_ir
from .ids import next_prefixed_id
from .layout_cleaner import clean_doc_ir, save_cleaned_doc_ir
from .reading_order import restore_reading_order


@dataclass(frozen=True)
class ParseResult:
    doc_id: str
    page_count: int
    block_count: int
    normalized_path: Path
    parser_engine: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _project_workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _find_java_bin_dir() -> Path | None:
    candidates: list[Path] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin")

    candidates.extend(
        [
            Path(r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin"),
            Path(r"C:\Users\000043ce\.cache\opencode\bin\kotlin-ls\jre\bin"),
        ]
    )

    for candidate in candidates:
        java_exe = candidate / "java.exe"
        if java_exe.exists():
            return candidate
    return None


def _load_opendataloader_convert():
    package_root = _project_workspace_root() / "opendataloader-pdf"
    if package_root.exists():
        root_str = str(package_root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

    try:
        from opendataloader_pdf import convert
    except ImportError:
        return None
    return convert


def _page_dimensions_from_pdf(source_path: Path) -> dict[int, tuple[float, float]]:
    document = fitz.open(source_path)
    try:
        return {
            page_index: (float(page.rect.width), float(page.rect.height))
            for page_index, page in enumerate(document, start=1)
        }
    finally:
        document.close()


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _load_paddlevl_settings() -> tuple[str, str]:
    _load_env_file(_project_workspace_root() / "KB" / "knowledge-base" / ".env")
    api_url = os.environ.get("PADDLEVL_API_URL")
    api_token = os.environ.get("PADDLEVL_API_TOKEN")
    if not api_url or not api_token:
        raise RuntimeError("PaddleVL configuration unavailable")
    return api_url, api_token


def _summarize_parsed_text(parsed_pages: list[dict[str, object]]) -> tuple[int, int]:
    block_count = 0
    total_chars = 0
    for page in parsed_pages:
        for block in page["blocks"]:
            text = str(block.get("text", "")).strip()
            if text:
                block_count += 1
                total_chars += len(text)
    return block_count, total_chars


def _estimate_text_anomaly(parsed_pages: list[dict[str, object]]) -> dict[str, float]:
    sample_text_parts: list[str] = []
    sampled_blocks = 0
    for page in parsed_pages[:5]:
        for block in page["blocks"][:20]:
            text = str(block.get("text", "")).strip()
            if text:
                sample_text_parts.append(text)
                sampled_blocks += 1
            if sampled_blocks >= 40:
                break
        if sampled_blocks >= 40:
            break

    sample_text = "\n".join(sample_text_parts)
    if not sample_text:
        return {"anomaly_ratio": 1.0, "fullwidth_ratio": 0.0}

    anomaly_chars = 0
    fullwidth_chars = 0
    counted_chars = 0

    for ch in sample_text:
        if ch.isspace():
            continue
        counted_chars += 1
        codepoint = ord(ch)
        if 0xFF01 <= codepoint <= 0xFF5E:
            fullwidth_chars += 1
        name = unicodedata.name(ch, "")
        if name.startswith("CJK UNIFIED IDEOGRAPH-") and ch not in {
            "中", "华", "人", "民", "共", "和", "国", "电", "动", "汽", "车", "用", "传", "导",
            "式", "车", "载", "充", "电", "机", "标", "准", "前", "言", "目", "次", "范", "围",
        }:
            anomaly_chars += 1
        elif "MATHEMATICAL" in name:
            anomaly_chars += 1

    if counted_chars == 0:
        return {"anomaly_ratio": 1.0, "fullwidth_ratio": 0.0}

    return {
        "anomaly_ratio": anomaly_chars / counted_chars,
        "fullwidth_ratio": fullwidth_chars / counted_chars,
    }


def _is_text_sparse(parsed_pages: list[dict[str, object]]) -> bool:
    page_count = len(parsed_pages)
    block_count, total_chars = _summarize_parsed_text(parsed_pages)
    anomaly = _estimate_text_anomaly(parsed_pages)
    if block_count == 0:
        return True
    if page_count >= 5 and block_count < max(5, page_count // 2):
        return True
    if page_count >= 5 and total_chars < page_count * 40:
        return True
    if anomaly["anomaly_ratio"] > 0.08:
        return True
    if anomaly["fullwidth_ratio"] > 0.35:
        return True
    return False


def _parse_pdf_with_opendataloader(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    convert = _load_opendataloader_convert()
    java_bin_dir = _find_java_bin_dir()
    if convert is None or java_bin_dir is None:
        raise RuntimeError("opendataloader-pdf or java runtime unavailable")

    os.environ["PATH"] = str(java_bin_dir) + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault(
        "JAVA_TOOL_OPTIONS",
        "-Xms128m -Xmx768m -XX:+UseSerialGC",
    )
    page_dimensions = _page_dimensions_from_pdf(source_path)

    temp_root = _project_workspace_root() / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="eakb_odl_", dir=str(temp_root)) as tmp_dir:
        output_dir = Path(tmp_dir)
        convert(
            input_path=str(source_path),
            output_dir=str(output_dir),
            format=["json"],
            quiet=True,
            reading_order="xycut",
            table_method="cluster",
        )

        json_path = output_dir / f"{source_path.stem}.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))

    grouped_blocks: dict[int, list[dict[str, object]]] = {}
    for index, item in enumerate(data.get("kids", []), start=1):
        page_no = int(item.get("page number", 1))
        grouped_blocks.setdefault(page_no, []).append(
            {
                "reading_order": index,
                "block_type": item.get("type", "text"),
                "text": item.get("content", "").strip(),
                "raw_text": item.get("content", ""),
                "bbox": item.get("bounding box"),
            }
        )

    parsed_pages: list[dict[str, object]] = []
    total_pages = int(data.get("number of pages", len(page_dimensions)))
    for page_no in range(1, total_pages + 1):
        width, height = page_dimensions.get(page_no, (None, None))
        blocks = [block for block in grouped_blocks.get(page_no, []) if block["text"]]
        parsed_pages.append(
            {
                "page_no": page_no,
                "width": width,
                "height": height,
                "parser_confidence": 1.0,
                "ocr_confidence": None,
                "risk_level": "unknown",
                "page_status": "parsed",
                "blocks": blocks,
            }
        )

    return "opendataloader", parsed_pages


def _parse_pdf_with_paddlevl(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    api_url, api_token = _load_paddlevl_settings()
    page_dimensions = _page_dimensions_from_pdf(source_path)

    file_bytes = source_path.read_bytes()
    file_size_mb = len(file_bytes) / (1024 * 1024)
    timeout = 180.0
    if file_size_mb > 20:
        timeout = 400.0
    elif file_size_mb > 10:
        timeout = 300.0

    headers = {
        "Authorization": f"token {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "file": base64.b64encode(file_bytes).decode("ascii"),
        "fileType": 0,
        "useDocOrientationClassify": True,
        "useDocUnwarping": True,
        "useChartRecognition": True,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()

    layout_results = result.get("result", {}).get("layoutParsingResults", [])
    parsed_pages: list[dict[str, object]] = []
    page_count = max(len(layout_results), len(page_dimensions))

    for page_no in range(1, page_count + 1):
        width, height = page_dimensions.get(page_no, (None, None))
        markdown_text = ""
        if page_no <= len(layout_results):
            markdown_text = (
                layout_results[page_no - 1]
                .get("markdown", {})
                .get("text", "")
                .strip()
            )

        blocks = []
        if markdown_text:
            blocks.append(
                {
                    "reading_order": 1,
                    "block_type": "ocr_markdown",
                    "text": markdown_text,
                    "raw_text": markdown_text,
                    "bbox": None,
                }
            )

        parsed_pages.append(
            {
                "page_no": page_no,
                "width": width,
                "height": height,
                "parser_confidence": 0.9,
                "ocr_confidence": 0.9,
                "risk_level": "unknown",
                "page_status": "parsed",
                "blocks": blocks,
            }
        )

    return "paddlevl", parsed_pages


def _parse_pdf_with_pymupdf(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    parsed_pages: list[dict[str, object]] = []
    document = fitz.open(source_path)
    try:
        for page_index, page in enumerate(document, start=1):
            blocks: list[dict[str, object]] = []
            for reading_order, block in enumerate(page.get_text("blocks"), start=1):
                x0, y0, x1, y1, text, _, block_type = block
                cleaned = (text or "").strip()
                if not cleaned:
                    continue

                blocks.append(
                    {
                        "reading_order": reading_order,
                        "block_type": "text" if int(block_type) == 0 else "image",
                        "text": cleaned,
                        "raw_text": text or "",
                        "bbox": [x0, y0, x1, y1],
                    }
                )

            parsed_pages.append(
                {
                    "page_no": page_index,
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                    "parser_confidence": 1.0,
                    "ocr_confidence": None,
                    "risk_level": "unknown",
                    "page_status": "parsed",
                    "blocks": blocks,
                }
            )
    finally:
        document.close()

    return "pymupdf", parsed_pages


def _parse_pdf(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    try:
        engine, parsed_pages = _parse_pdf_with_opendataloader(source_path)
        if _is_text_sparse(parsed_pages):
            return _parse_pdf_with_paddlevl(source_path)
        return engine, parsed_pages
    except Exception:
        try:
            return _parse_pdf_with_paddlevl(source_path)
        except Exception:
            return _parse_pdf_with_pymupdf(source_path)


def _parse_text(source_path: Path) -> list[dict[str, object]]:
    text = source_path.read_text(encoding="utf-8", errors="replace")
    raw_blocks = [part.strip() for part in text.split("\n\n")]
    blocks = [
        {
            "reading_order": index,
            "block_type": "text",
            "text": content,
            "raw_text": content,
            "bbox": None,
        }
        for index, content in enumerate(raw_blocks, start=1)
        if content
    ]
    return [
        {
            "page_no": 1,
            "width": None,
            "height": None,
            "parser_confidence": 0.95,
            "ocr_confidence": None,
            "risk_level": "unknown",
            "page_status": "parsed",
            "blocks": blocks,
        }
    ]


def _select_parser(source_type: str):
    if source_type == "pdf":
        return _parse_pdf
    if source_type in {"markdown", "text", "file"}:
        return _parse_text
    raise ValueError(f"unsupported source_type for parse: {source_type}")


def parse_document(workspace_root: Path, doc_id: str) -> ParseResult:
    paths = AppPaths.from_root(workspace_root)
    now = _utc_now()
    connection = connect(paths.db_file)

    try:
        document_row = connection.execute(
            """
            SELECT doc_id, source_path, source_type
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document_row is None:
            raise ValueError(f"document not found: {doc_id}")

        parser = _select_parser(document_row["source_type"])
        source_path = Path(document_row["source_path"])
        parser_engine = "text"
        if document_row["source_type"] == "pdf":
            parser_engine, parsed_pages = parser(source_path)
        else:
            parsed_pages = parser(source_path)

        doc_ir = build_doc_ir(
            doc_id=doc_id,
            parser_engine=parser_engine,
            source_type=str(document_row["source_type"]),
            parsed_pages=parsed_pages,
        )

        connection.execute("DELETE FROM blocks WHERE doc_id = ?", (doc_id,))
        connection.execute("DELETE FROM pages WHERE doc_id = ?", (doc_id,))

        block_count = 0
        persisted_pages: list[dict[str, object]] = []

        for page_payload in parsed_pages:
            page_id = next_prefixed_id(connection, "page", "PAGE")
            connection.execute(
                """
                INSERT INTO pages (
                    page_id, doc_id, page_no, width, height, parser_confidence,
                    ocr_confidence, risk_level, page_status, screenshot_path,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    doc_id,
                    page_payload["page_no"],
                    page_payload["width"],
                    page_payload["height"],
                    page_payload["parser_confidence"],
                    page_payload["ocr_confidence"],
                    page_payload["risk_level"],
                    page_payload["page_status"],
                    None,
                    now,
                    now,
                ),
            )

            persisted_blocks: list[dict[str, object]] = []
            for block_payload in page_payload["blocks"]:
                block_id = next_prefixed_id(connection, "block", "BLK")
                connection.execute(
                    """
                    INSERT INTO blocks (
                        block_id, page_id, doc_id, block_type, reading_order,
                        text_content, raw_text, bbox_json, parser_confidence,
                        ocr_confidence, risk_flags_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        block_id,
                        page_id,
                        doc_id,
                        block_payload["block_type"],
                        block_payload["reading_order"],
                        block_payload["text"],
                        block_payload["raw_text"],
                        json.dumps(block_payload["bbox"], ensure_ascii=False)
                        if block_payload["bbox"] is not None
                        else None,
                        page_payload["parser_confidence"],
                        page_payload["ocr_confidence"],
                        json.dumps([], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                block_count += 1
                persisted_blocks.append(
                    {
                        "block_id": block_id,
                        "block_type": block_payload["block_type"],
                        "reading_order": block_payload["reading_order"],
                        "text": block_payload["text"],
                        "bbox": block_payload["bbox"],
                    }
                )

            persisted_pages.append(
                {
                    "page_id": page_id,
                    "page_no": page_payload["page_no"],
                    "width": page_payload["width"],
                    "height": page_payload["height"],
                    "blocks": persisted_blocks,
                }
            )

        normalized_path = paths.normalized / f"{doc_id}.json"
        normalized_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "parsed_at": now,
                    "parser_engine": parser_engine,
                    "page_count": len(persisted_pages),
                    "block_count": block_count,
                    "pages": persisted_pages,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        doc_ir_path = paths.normalized / f"{doc_id}.doc_ir.json"
        save_doc_ir(doc_ir, doc_ir_path)
        cleaned_doc_ir = restore_reading_order(clean_doc_ir(doc_ir))
        cleaned_doc_ir_path = paths.normalized / f"{doc_id}.cleaned_doc_ir.json"
        save_cleaned_doc_ir(cleaned_doc_ir, cleaned_doc_ir_path)

        connection.execute(
            """
            UPDATE documents
            SET page_count = ?, parse_status = ?, update_time = ?
            WHERE doc_id = ?
            """,
            (len(persisted_pages), "parsed", now, doc_id),
        )
        connection.commit()
        return ParseResult(
            doc_id=doc_id,
            page_count=len(persisted_pages),
            block_count=block_count,
            normalized_path=normalized_path,
            parser_engine=parser_engine,
        )
    finally:
        connection.close()
