from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_tools import run_agent_query
from .answer_api import answer_query
from .api_server import serve_api
from .mcp_server import run_mcp_stdio
from .bootstrap import initialize_workspace, workspace_status
from .evidence import build_evidence_for_document
from .entities import build_entities_for_document
from .facts import build_facts_for_document
from .graph import build_graph_for_document
from .governance import assess_pending_quality
from .ingest import register_document
from .jobs import run_parse_jobs, summarize_job_results
from .parse import parse_document
from .pipeline import run_batch_pipeline, run_document_pipeline, run_file_pipeline
from .query_api import build_query_context
from .quality import assess_document_quality
from .retrieval import search_knowledge_base
from .wiki_compiler import build_wiki_for_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eakb",
        description="Enterprise agent knowledge base bootstrap CLI.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("knowledge_base"),
        help="Workspace root directory for the knowledge base.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create the workspace layout and SQLite schema.")
    subparsers.add_parser("status", help="Print workspace and database status.")

    register_parser = subparsers.add_parser(
        "register",
        help="Register a source document into the knowledge base.",
    )
    register_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file to ingest.",
    )

    parse_parser = subparsers.add_parser(
        "parse-document",
        help="Parse a registered document into pages and blocks.",
    )
    parse_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to parse.",
    )

    jobs_parser = subparsers.add_parser(
        "run-jobs",
        help="Run pending background jobs.",
    )
    jobs_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of jobs to execute.",
    )

    quality_parser = subparsers.add_parser(
        "quality-document",
        help="Assess quality for a parsed document.",
    )
    quality_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to assess.",
    )

    quality_batch_parser = subparsers.add_parser(
        "quality-batch",
        help="Assess quality for parsed documents.",
    )
    quality_batch_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of documents to assess.",
    )

    evidence_parser = subparsers.add_parser(
        "build-evidence",
        help="Build evidence objects for a quality-assessed document.",
    )
    evidence_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build evidence for.",
    )

    facts_parser = subparsers.add_parser(
        "build-facts",
        help="Build facts for an evidenced document.",
    )
    facts_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build facts for.",
    )

    entities_parser = subparsers.add_parser(
        "build-entities",
        help="Build entities and attach facts for a document.",
    )
    entities_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build entities for.",
    )

    wiki_parser = subparsers.add_parser(
        "build-wiki",
        help="Build wiki pages for a document.",
    )
    wiki_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build wiki for.",
    )

    graph_parser = subparsers.add_parser(
        "build-graph",
        help="Build graph edges for a document.",
    )
    graph_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build graph for.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search evidence, facts, and wiki pages.",
    )
    search_parser.add_argument(
        "--query",
        required=True,
        help="Search query.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results.",
    )

    query_parser = subparsers.add_parser(
        "query-context",
        help="Build structured retrieval context for agents.",
    )
    query_parser.add_argument(
        "--query",
        required=True,
        help="Query text.",
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of search hits to expand.",
    )

    answer_parser = subparsers.add_parser(
        "answer-query",
        help="Build an explainable answer from structured query context.",
    )
    answer_parser.add_argument(
        "--query",
        required=True,
        help="Question or query text.",
    )
    answer_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of search hits to expand.",
    )

    agent_parser = subparsers.add_parser(
        "agent-query",
        help="Run a lightweight multi-hop agent query over the knowledge base.",
    )
    agent_parser.add_argument(
        "--query",
        required=True,
        help="Question or query text.",
    )
    agent_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of search hits per tool call.",
    )

    build_document_parser = subparsers.add_parser(
        "build-document",
        help="Run the full pipeline for a registered document.",
    )
    build_document_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build end-to-end.",
    )

    build_file_parser = subparsers.add_parser(
        "build-file",
        help="Register a source file and run the full pipeline.",
    )
    build_file_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file.",
    )

    build_batch_parser = subparsers.add_parser(
        "build-batch",
        help="Run the full pipeline for multiple registered documents.",
    )
    build_batch_parser.add_argument(
        "--doc-ids",
        nargs="+",
        required=True,
        help="One or more document IDs.",
    )

    serve_parser = subparsers.add_parser(
        "serve-api",
        help="Start the local HTTP API server.",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind.",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind.",
    )

    mcp_parser = subparsers.add_parser(
        "serve-mcp",
        help="Start the stdio MCP server.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    schema_path = Path(__file__).with_name("schema.sql")

    if args.command == "init":
        paths = initialize_workspace(args.root, schema_path)
        print(f"initialized workspace: {paths.root}")
        print(f"database: {paths.db_file}")
        return

    if args.command == "status":
        status = workspace_status(args.root)
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    if args.command == "register":
        result = register_document(args.root, args.file)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "job_id": result.job_id,
                    "deduplicated": result.deduplicated,
                    "stored_path": str(result.stored_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "parse-document":
        result = parse_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "page_count": result.page_count,
                    "block_count": result.block_count,
                    "normalized_path": str(result.normalized_path),
                    "parser_engine": result.parser_engine,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "run-jobs":
        results = run_parse_jobs(args.root, limit=args.limit)
        print(json.dumps(summarize_job_results(results), indent=2, ensure_ascii=False))
        return

    if args.command == "quality-document":
        result = assess_document_quality(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "overall_score": result.overall_score,
                    "high_risk_page_count": result.high_risk_page_count,
                    "review_required_count": result.review_required_count,
                    "blocked_count": result.blocked_count,
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "quality-batch":
        results = assess_pending_quality(args.root, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.command == "build-evidence":
        result = build_evidence_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "evidence_count": result.evidence_count,
                    "skipped_block_count": result.skipped_block_count,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-facts":
        result = build_facts_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "fact_count": result.fact_count,
                    "fact_types": result.fact_types,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-entities":
        result = build_entities_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "entity_count": result.entity_count,
                    "entity_types": result.entity_types,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-wiki":
        result = build_wiki_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "page_count": result.page_count,
                    "export_paths": [str(path) for path in result.export_paths],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-graph":
        result = build_graph_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "edge_count": result.edge_count,
                    "edge_types": result.edge_types,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "search":
        results = search_knowledge_base(args.root, args.query, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.command == "query-context":
        result = build_query_context(args.root, args.query, limit=args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "answer-query":
        result = answer_query(args.root, args.query, limit=args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "agent-query":
        result = run_agent_query(args.root, args.query, limit=args.limit)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-document":
        result = run_document_pipeline(args.root, args.doc_id)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-file":
        result = run_file_pipeline(args.root, args.file)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-batch":
        results = run_batch_pipeline(args.root, args.doc_ids)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.command == "serve-api":
        serve_api(args.root, host=args.host, port=args.port)
        return

    if args.command == "serve-mcp":
        run_mcp_stdio(args.root)
        return

    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
