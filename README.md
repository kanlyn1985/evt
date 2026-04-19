# Enterprise Agent Knowledge Base

This repository bootstraps a new enterprise-grade agent knowledge base project from the V2 technical implementation document.

## Current scope

The first milestone establishes:

- a Python package and CLI entry point
- a canonical on-disk knowledge base layout
- a SQLite schema aligned with the technical design
- a repeatable `init` flow to create a local workspace
- a minimal ingest registration flow with dedupe and parse job enqueue
- a minimal parse pipeline for PDF and plain text style documents

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
eakb init
eakb status
eakb register --file "E:\path\to\document.pdf"
eakb run-jobs
eakb serve-api --host 127.0.0.1 --port 8000
```

## Test commands

Fast local tests:

```bash
pytest -q
```

Integration tests:

```bash
pytest -q -m integration
```

Query and answer regression benchmarks:

```bash
pytest -q -m benchmark
```

Note:

- default `pytest -q` excludes `integration` and `benchmark`
- pytest uses a local `.pytest-tmp/` base temp directory to avoid Windows temp permission issues in this environment

## HTTP API

Start the local API server:

```bash
eakb serve-api --host 127.0.0.1 --port 8000
```

Available endpoints:

- `GET /health`
- `POST /search`
- `POST /query-context`
- `POST /answer-query`
- `POST /agent-query`
- `POST /build-document`

## MCP Server

Start the stdio MCP server:

```bash
eakb serve-mcp
```

Minimal JSON-RPC example:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"answer_query","arguments":{"query":"什么是控制导引电路？","limit":4}}}
```

Available MCP tools:

- `search`
- `query_context`
- `answer_query`
- `agent_query`
- `build_document`

## Client Examples

HTTP client example:

```bash
python examples/http_client_example.py
```

MCP stdio client example:

```bash
python examples/mcp_client_example.py
```

Suggested local flow:

1. Start the server:
   `eakb serve-api --host 127.0.0.1 --port 8000`
2. Run the HTTP example:
   `python examples/http_client_example.py`
3. Or run the MCP example directly:
   `python examples/mcp_client_example.py`

## One-Click Launch

PowerShell:

```powershell
.\launch.ps1
```

Batch:

```bat
start_demo.bat
```

This starts the local HTTP API, opens the demo page, and prints the most useful test commands.

## Delivery Notes

See [docs/final_delivery_notes.md](docs/final_delivery_notes.md) for the final capability summary, test layers, known limitations, and workspace hygiene notes.

By default, the CLI creates a `knowledge_base/` directory in the current working directory with:

- `raw/`
- `normalized/`
- `evidence/`
- `facts/`
- `wiki/`
- `review_queue/`
- `quality_reports/`
- `logs/`
- `db/knowledge.db`

## Milestone plan

1. Foundation: project skeleton, schema, initialization, job lifecycle baseline
2. Ingest: document registration, hashing, dedupe, job enqueue
3. Parse: PDF/text parsing into pages and blocks
4. Quality gate: page risk scoring and review queue generation
5. Evidence and facts: evidence extraction, entity/fact generation, linkage
6. Wiki and retrieval: wiki compiler, FTS, graph, MCP-facing query layer
7. Governance: incremental rebuilds, dependency propagation, auditing

## Design alignment

The implementation is based on the technical design document located at:

`E:\chome download\hil_sim\enterprise_agent_knowledgebase_v_2_techimpl.md`
