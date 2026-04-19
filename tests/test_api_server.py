from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from enterprise_agent_kb.api_server import ApiServer


WORKSPACE = Path("knowledge_base")


@pytest.mark.unit
def test_api_health_and_answer_query() -> None:
    server = ApiServer(("127.0.0.1", 0), WORKSPACE)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=120)

    try:
        conn.request("GET", "/health")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "ok"
        assert payload["server"]["name"] == "enterprise-agent-kb"
        assert "started_at" in payload["server"]

        conn.request("GET", "/demo")
        response = conn.getresponse()
        assert response.status == 200
        html = response.read().decode("utf-8")
        assert "企业级知识库工作台" in html
        assert "执行查询" in html
        assert "检查接口" in html

        conn.request("GET", "/documents")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "documents" in payload
        assert isinstance(payload["documents"], list)

        body = json.dumps({"query": "什么是控制导引电路？", "limit": 4})
        conn.request(
            "POST",
            "/answer-query",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "direct_answer" in payload
        assert "控制导引电路" in payload["direct_answer"]

        body = json.dumps({"doc_id": "DOC-000006"})
        conn.request(
            "POST",
            "/generate-golden-tests",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == "DOC-000006"
        assert payload["case_count"] >= 20
        assert payload["local_case_count"] >= 1
        assert payload["page_coverage_count"] >= 10

        body = json.dumps({"doc_id": "DOC-000006"})
        conn.request(
            "POST",
            "/run-golden-tests",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == "DOC-000006"
        assert "passed" in payload
        assert "failed" in payload
        assert "success" in payload

        body = json.dumps({"doc_id": "DOC-000006"})
        conn.request(
            "POST",
            "/start-build-document",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 202
        payload = json.loads(response.read().decode("utf-8"))
        job_id = payload["job_id"]

        body = json.dumps({"job_id": job_id})
        conn.request(
            "POST",
            "/job-status",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["job_id"] == job_id
        assert payload["status"] in {"queued", "running", "completed"}
        assert "history" in payload

        conn.request("GET", "/jobs")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "jobs" in payload

        conn.request("GET", "/audit-log")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "events" in payload
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
