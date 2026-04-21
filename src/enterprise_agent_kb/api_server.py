from __future__ import annotations

import json
import tempfile
import base64
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from datetime import UTC, datetime

from .agent_tools import run_agent_query
from .answer_api import answer_query
from .config import AppPaths
from .doc_diagnostics import build_document_diagnostics
from .generated_tests import generate_golden_tests_for_document, run_golden_tests_for_document
from .pipeline import run_document_pipeline, run_document_pipeline_and_tests
from .parse import parse_document
from .quality import assess_document_quality
from .evidence import build_evidence_for_document
from .facts import build_facts_for_document
from .entities import build_entities_for_document
from .wiki_compiler import build_wiki_for_document
from .graph import build_graph_for_document
from .ingest import register_document
from .query_api import build_query_context
from .retrieval import search_knowledge_base
from . import __version__


class ApiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], workspace_root: Path):
        self.workspace_root = workspace_root
        self.project_root = Path(__file__).resolve().parents[2]
        self.started_at = datetime.now(UTC).isoformat(timespec="seconds")
        self.jobs: dict[str, dict[str, Any]] = {}
        self.jobs_lock = threading.Lock()
        self.audit_log_path = self.workspace_root / "logs" / "audit_log.jsonl"
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_lock = threading.Lock()
        super().__init__(server_address, ApiRequestHandler)


class ApiRequestHandler(BaseHTTPRequestHandler):
    server: ApiServer

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_common_headers("application/json; charset=utf-8", 0)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "server": {
                        "name": "enterprise-agent-kb",
                        "version": __version__,
                        "started_at": self.server.started_at,
                        "workspace_root": str(self.server.workspace_root),
                    },
                },
            )
            return
        if parsed.path == "/documents":
            self._write_json(HTTPStatus.OK, {"documents": self._list_documents()})
            return
        if parsed.path == "/jobs":
            self._write_json(HTTPStatus.OK, {"jobs": self._list_jobs()})
            return
        if parsed.path == "/audit-log":
            self._write_json(HTTPStatus.OK, {"events": self._read_audit_events()})
            return
        if parsed.path in {"/", "/demo"}:
            self._write_file(self.server.project_root / "examples" / "demo.html", "text/html; charset=utf-8")
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if body is None:
            return

        routes = {
            "/search": self._handle_search,
            "/query-context": self._handle_query_context,
            "/answer-query": self._handle_answer_query,
            "/agent-query": self._handle_agent_query,
            "/build-document": self._handle_build_document,
            "/build-document-and-test": self._handle_build_document_and_test,
            "/convert-document": self._handle_convert_document,
            "/upload-build": self._handle_upload_build,
            "/upload-build-and-test": self._handle_upload_build_and_test,
            "/upload-convert": self._handle_upload_convert,
            "/start-build-document": self._handle_start_build_document,
            "/start-build-document-and-test": self._handle_start_build_document_and_test,
            "/start-convert-document": self._handle_start_convert_document,
            "/start-upload-build": self._handle_start_upload_build,
            "/start-upload-build-and-test": self._handle_start_upload_build_and_test,
            "/start-upload-convert": self._handle_start_upload_convert,
            "/job-status": self._handle_job_status,
            "/document-detail": self._handle_document_detail,
            "/document-diagnostics": self._handle_document_diagnostics,
            "/generate-golden-tests": self._handle_generate_golden_tests,
            "/run-golden-tests": self._handle_run_golden_tests,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        try:
            handler(body)
        except Exception as exc:  # pragma: no cover - last-resort API guard
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "message": str(exc)},
            )

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_search(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 10))
        result = search_knowledge_base(self.server.workspace_root, query, limit=limit)
        self._record_audit("search", {"query": query, "limit": limit, "result_count": len(result)})
        self._write_json(HTTPStatus.OK, {"results": result})

    def _handle_query_context(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 8))
        preferred_doc_id = str(body.get("preferred_doc_id", "")).strip() or None
        result = build_query_context(self.server.workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
        self._record_audit("query_context", {"query": query, "limit": limit, "hit_count": result.get("hit_count", 0)})
        self._write_json(HTTPStatus.OK, result)

    def _handle_answer_query(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 8))
        preferred_doc_id = str(body.get("preferred_doc_id", "")).strip() or None
        result = answer_query(self.server.workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
        self._record_audit(
            "answer_query",
            {"query": query, "limit": limit, "direct_answer": str(result.get("direct_answer", ""))[:200]},
        )
        self._write_json(HTTPStatus.OK, result)

    def _handle_agent_query(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 8))
        result = run_agent_query(self.server.workspace_root, query, limit=limit)
        self._record_audit(
            "agent_query",
            {"query": query, "limit": limit, "plan_steps": len(result.plan)},
        )
        self._write_json(
            HTTPStatus.OK,
            {
                "query": result.query,
                "plan": result.plan,
                "tool_results": result.tool_results,
                "final_answer": result.final_answer,
            },
        )

    def _handle_build_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = run_document_pipeline(self.server.workspace_root, doc_id)
        self._record_audit("build_document", {"doc_id": doc_id, "result": result.__dict__})
        self._write_json(HTTPStatus.OK, result.__dict__)

    def _handle_convert_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = parse_document(self.server.workspace_root, doc_id)
        payload = {
            "doc_id": result.doc_id,
            "page_count": result.page_count,
            "block_count": result.block_count,
            "normalized_path": str(result.normalized_path),
            "parser_engine": result.parser_engine,
            "mode": "convert_only",
        }
        self._record_audit("convert_document", {"doc_id": doc_id, "result": payload})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_build_document_and_test(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = run_document_pipeline_and_tests(self.server.workspace_root, doc_id)
        self._record_audit("build_document_and_test", {"doc_id": doc_id, "result": result.__dict__})
        self._write_json(HTTPStatus.OK, result.__dict__)

    def _handle_upload_build(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return

        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / filename
            temp_path.write_bytes(base64.b64decode(content_base64))
            register_result = register_document(self.server.workspace_root, temp_path)
            pipeline_result = run_document_pipeline(self.server.workspace_root, register_result.doc_id)

        self._write_json(
            HTTPStatus.OK,
            {
                "doc_id": pipeline_result.doc_id,
                "registered": True,
                "deduplicated": register_result.deduplicated,
                "parser_engine": pipeline_result.parser_engine,
                "page_count": pipeline_result.page_count,
                "block_count": pipeline_result.block_count,
                "overall_score": pipeline_result.overall_score,
                "evidence_count": pipeline_result.evidence_count,
                "fact_count": pipeline_result.fact_count,
                "entity_count": pipeline_result.entity_count,
                "wiki_page_count": pipeline_result.wiki_page_count,
                "edge_count": pipeline_result.edge_count,
            },
        )

    def _handle_upload_convert(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return

        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / filename
            temp_path.write_bytes(base64.b64decode(content_base64))
            register_result = register_document(self.server.workspace_root, temp_path)
            parse_result = parse_document(self.server.workspace_root, register_result.doc_id)

        self._write_json(
            HTTPStatus.OK,
            {
                "doc_id": parse_result.doc_id,
                "registered": True,
                "deduplicated": register_result.deduplicated,
                "page_count": parse_result.page_count,
                "block_count": parse_result.block_count,
                "normalized_path": str(parse_result.normalized_path),
                "parser_engine": parse_result.parser_engine,
                "mode": "convert_only",
            },
        )

    def _handle_upload_build_and_test(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return

        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / filename
            temp_path.write_bytes(base64.b64decode(content_base64))
            register_result = register_document(self.server.workspace_root, temp_path)
            result = run_document_pipeline_and_tests(self.server.workspace_root, register_result.doc_id)

        payload = result.__dict__.copy()
        payload["registered"] = True
        payload["deduplicated"] = register_result.deduplicated
        self._write_json(HTTPStatus.OK, payload)

    def _handle_start_build_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        job_id = self._create_job("build_document", {"doc_id": doc_id})
        self._record_audit("start_build_document", {"doc_id": doc_id, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_convert_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        job_id = self._create_job("convert_document", {"doc_id": doc_id})
        self._record_audit("start_convert_document", {"doc_id": doc_id, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_build_document_and_test(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        job_id = self._create_job("build_document_and_test", {"doc_id": doc_id})
        self._record_audit("start_build_document_and_test", {"doc_id": doc_id, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_upload_build(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return
        job_id = self._create_job(
            "upload_build",
            {"filename": filename, "content_base64": content_base64},
        )
        self._record_audit("start_upload_build", {"filename": filename, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_upload_convert(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return
        job_id = self._create_job(
            "upload_convert",
            {"filename": filename, "content_base64": content_base64},
        )
        self._record_audit("start_upload_convert", {"filename": filename, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_upload_build_and_test(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return
        job_id = self._create_job(
            "upload_build_and_test",
            {"filename": filename, "content_base64": content_base64},
        )
        self._record_audit("start_upload_build_and_test", {"filename": filename, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_job_status(self, body: dict[str, Any]) -> None:
        job_id = str(body.get("job_id", "")).strip()
        if not job_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "job_id_required"})
            return
        with self.server.jobs_lock:
            payload = self.server.jobs.get(job_id)
        if payload is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "job_not_found", "job_id": job_id})
            return
        self._write_json(HTTPStatus.OK, payload)

    def _handle_document_detail(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        detail = self._document_detail(doc_id)
        self._record_audit("document_detail", {"doc_id": doc_id})
        self._write_json(HTTPStatus.OK, detail)

    def _handle_document_diagnostics(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        detail = build_document_diagnostics(self.server.workspace_root, doc_id)
        self._record_audit("document_diagnostics", {"doc_id": doc_id})
        self._write_json(HTTPStatus.OK, detail)

    def _handle_generate_golden_tests(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        result = generate_golden_tests_for_document(self.server.workspace_root, doc_id)
        self._record_audit("generate_golden_tests", {"doc_id": doc_id, "case_count": result["case_count"]})
        self._write_json(HTTPStatus.OK, result)

    def _handle_run_golden_tests(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        result = run_golden_tests_for_document(self.server.workspace_root, doc_id)
        self._record_audit(
            "run_golden_tests",
            {"doc_id": doc_id, "success": result["success"], "passed": result["passed"], "failed": result["failed"]},
        )
        self._write_json(HTTPStatus.OK, result)

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._write_common_headers("application/json; charset=utf-8", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._write_common_headers(content_type, len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _write_common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _create_job(self, job_type: str, payload: dict[str, Any]) -> str:
        job_id = f"api-job-{uuid.uuid4().hex}"
        job = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "history": [{"stage": "queued", "progress": 0}],
            "result": None,
            "error": None,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with self.server.jobs_lock:
            self.server.jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, job_type, payload),
            daemon=True,
        )
        thread.start()
        return job_id

    def _run_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        try:
            self._update_job(job_id, status="running", progress=5, stage="starting")
            if job_type == "build_document":
                result = self._run_document_pipeline_with_updates(job_id, str(payload["doc_id"]))
            elif job_type == "build_document_and_test":
                result = self._run_document_pipeline_and_test_with_updates(job_id, str(payload["doc_id"]))
            elif job_type == "convert_document":
                result = self._run_convert_document_with_updates(job_id, str(payload["doc_id"]))
            elif job_type == "upload_build":
                result = self._run_upload_pipeline_with_updates(job_id, payload)
            elif job_type == "upload_build_and_test":
                result = self._run_upload_pipeline_and_test_with_updates(job_id, payload)
            elif job_type == "upload_convert":
                result = self._run_upload_convert_with_updates(job_id, payload)
            else:
                raise ValueError(f"unsupported job type: {job_type}")
            self._update_job(job_id, status="completed", progress=100, stage="completed", result=result)
        except Exception as exc:
            self._update_job(job_id, status="failed", stage="failed", error=str(exc))

    def _run_document_pipeline_with_updates(self, job_id: str, doc_id: str) -> dict[str, Any]:
        self._update_job(job_id, progress=15, stage="parse")
        parse_result = parse_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=30, stage="quality")
        quality_result = assess_document_quality(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=45, stage="evidence")
        evidence_result = build_evidence_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=60, stage="facts")
        facts_result = build_facts_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=72, stage="entities")
        entities_result = build_entities_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=84, stage="wiki")
        wiki_result = build_wiki_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=94, stage="graph")
        graph_result = build_graph_for_document(self.server.workspace_root, doc_id)
        return {
            "doc_id": doc_id,
            "parser_engine": parse_result.parser_engine,
            "page_count": parse_result.page_count,
            "block_count": parse_result.block_count,
            "overall_score": quality_result.overall_score,
            "evidence_count": evidence_result.evidence_count,
            "fact_count": facts_result.fact_count,
            "entity_count": entities_result.entity_count,
            "wiki_page_count": wiki_result.page_count,
            "edge_count": graph_result.edge_count,
        }

    def _run_upload_pipeline_with_updates(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / str(payload["filename"])
            temp_path.write_bytes(base64.b64decode(str(payload["content_base64"])))
            self._update_job(job_id, progress=10, stage="ingest")
            register_result = register_document(self.server.workspace_root, temp_path)
            result = self._run_document_pipeline_with_updates(job_id, register_result.doc_id)
            result["registered"] = True
            result["deduplicated"] = register_result.deduplicated
            return result

    def _run_convert_document_with_updates(self, job_id: str, doc_id: str) -> dict[str, Any]:
        self._update_job(job_id, progress=20, stage="parse")
        parse_result = parse_document(self.server.workspace_root, doc_id)
        return {
            "doc_id": doc_id,
            "parser_engine": parse_result.parser_engine,
            "page_count": parse_result.page_count,
            "block_count": parse_result.block_count,
            "normalized_path": str(parse_result.normalized_path),
            "mode": "convert_only",
        }

    def _run_upload_convert_with_updates(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / str(payload["filename"])
            temp_path.write_bytes(base64.b64decode(str(payload["content_base64"])))
            self._update_job(job_id, progress=10, stage="ingest")
            register_result = register_document(self.server.workspace_root, temp_path)
            result = self._run_convert_document_with_updates(job_id, register_result.doc_id)
            result["registered"] = True
            result["deduplicated"] = register_result.deduplicated
            return result

    def _run_document_pipeline_and_test_with_updates(self, job_id: str, doc_id: str) -> dict[str, Any]:
        result = self._run_document_pipeline_with_updates(job_id, doc_id)
        self._update_job(job_id, progress=96, stage="golden_generate")
        golden_result = generate_golden_tests_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=98, stage="golden_run")
        golden_run = run_golden_tests_for_document(self.server.workspace_root, doc_id)
        result.update(
            {
                "golden_case_count": int(golden_result.get("case_count", 0)),
                "golden_network_case_count": int(golden_result.get("network_case_count", 0)),
                "golden_local_case_count": int(golden_result.get("local_case_count", 0)),
                "golden_test_success": bool(golden_run.get("success", False)),
                "golden_test_passed": int(golden_run.get("passed", 0)),
                "golden_test_failed": int(golden_run.get("failed", 0)),
            }
        )
        return result

    def _run_upload_pipeline_and_test_with_updates(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / str(payload["filename"])
            temp_path.write_bytes(base64.b64decode(str(payload["content_base64"])))
            self._update_job(job_id, progress=10, stage="ingest")
            register_result = register_document(self.server.workspace_root, temp_path)
            result = self._run_document_pipeline_and_test_with_updates(job_id, register_result.doc_id)
            result["registered"] = True
            result["deduplicated"] = register_result.deduplicated
            return result

    def _update_job(self, job_id: str, **updates: Any) -> None:
        with self.server.jobs_lock:
            if job_id not in self.server.jobs:
                return
            stage = updates.get("stage")
            progress = updates.get("progress")
            if stage is not None:
                history = self.server.jobs[job_id].setdefault("history", [])
                if not history or history[-1].get("stage") != stage:
                    history.append(
                        {
                            "stage": stage,
                            "progress": progress if progress is not None else self.server.jobs[job_id].get("progress", 0),
                        }
                    )
            self.server.jobs[job_id].update(updates)

    def _list_jobs(self) -> list[dict[str, Any]]:
        with self.server.jobs_lock:
            jobs = list(self.server.jobs.values())
        jobs.sort(key=lambda item: item["created_at"], reverse=True)
        return jobs[:30]

    def _record_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "payload": payload,
        }
        with self.server.audit_lock:
            with self.server.audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_audit_events(self) -> list[dict[str, Any]]:
        if not self.server.audit_log_path.exists():
            return []
        lines = self.server.audit_log_path.read_text(encoding="utf-8").splitlines()
        events = []
        for line in reversed(lines[-100:]):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _list_documents(self) -> list[dict[str, Any]]:
        from .db import connect

        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            rows = connection.execute(
                """
                SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
                FROM documents
                ORDER BY ingest_time DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def _document_detail(self, doc_id: str) -> dict[str, Any]:
        from .db import connect

        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            document = connection.execute(
                """
                SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
                FROM documents
                WHERE doc_id = ?
                """,
                (doc_id,),
            ).fetchone()
            if document is None:
                return {"error": "document_not_found", "doc_id": doc_id}

            counts = {
                "pages": connection.execute("SELECT count(*) FROM pages WHERE doc_id = ?", (doc_id,)).fetchone()[0],
                "blocks": connection.execute("SELECT count(*) FROM blocks WHERE doc_id = ?", (doc_id,)).fetchone()[0],
                "evidence": connection.execute("SELECT count(*) FROM evidence WHERE doc_id = ?", (doc_id,)).fetchone()[0],
                "facts": connection.execute("SELECT count(*) FROM facts WHERE source_doc_id = ?", (doc_id,)).fetchone()[0],
                "wiki_pages": connection.execute(
                    "SELECT count(*) FROM wiki_pages WHERE json_extract(source_doc_ids_json, '$[0]') = ?",
                    (doc_id,),
                ).fetchone()[0],
                "graph_edges": connection.execute("SELECT count(*) FROM graph_edges WHERE version_scope = ?", (doc_id,)).fetchone()[0],
            }
            quality = connection.execute(
                """
                SELECT overall_score, high_risk_page_count, review_required_count, blocked_count
                FROM quality_reports
                WHERE doc_id = ?
                """,
                (doc_id,),
            ).fetchone()
            return {
                "document": dict(document),
                "counts": counts,
                "quality": dict(quality) if quality else None,
            }
        finally:
            connection.close()


def serve_api(workspace_root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ApiServer((host, port), workspace_root)
    try:
        server.serve_forever()
    finally:
        server.server_close()
