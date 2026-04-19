from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .entities import build_entities_for_document
from .evidence import build_evidence_for_document
from .facts import build_facts_for_document
from .graph import build_graph_for_document
from .ingest import register_document
from .parse import parse_document
from .quality import assess_document_quality
from .wiki_compiler import build_wiki_for_document


@dataclass(frozen=True)
class PipelineResult:
    doc_id: str
    registered: bool
    deduplicated: bool
    parser_engine: str
    page_count: int
    block_count: int
    overall_score: float
    evidence_count: int
    fact_count: int
    entity_count: int
    wiki_page_count: int
    edge_count: int


def run_document_pipeline(workspace_root: Path, doc_id: str) -> PipelineResult:
    parse_result = parse_document(workspace_root, doc_id)
    quality_result = assess_document_quality(workspace_root, doc_id)
    evidence_result = build_evidence_for_document(workspace_root, doc_id)
    facts_result = build_facts_for_document(workspace_root, doc_id)
    entities_result = build_entities_for_document(workspace_root, doc_id)
    wiki_result = build_wiki_for_document(workspace_root, doc_id)
    graph_result = build_graph_for_document(workspace_root, doc_id)

    return PipelineResult(
        doc_id=doc_id,
        registered=False,
        deduplicated=False,
        parser_engine=parse_result.parser_engine,
        page_count=parse_result.page_count,
        block_count=parse_result.block_count,
        overall_score=quality_result.overall_score,
        evidence_count=evidence_result.evidence_count,
        fact_count=facts_result.fact_count,
        entity_count=entities_result.entity_count,
        wiki_page_count=wiki_result.page_count,
        edge_count=graph_result.edge_count,
    )


def run_file_pipeline(workspace_root: Path, source_file: Path) -> PipelineResult:
    register_result = register_document(workspace_root, source_file)
    result = run_document_pipeline(workspace_root, register_result.doc_id)
    return PipelineResult(
        doc_id=result.doc_id,
        registered=True,
        deduplicated=register_result.deduplicated,
        parser_engine=result.parser_engine,
        page_count=result.page_count,
        block_count=result.block_count,
        overall_score=result.overall_score,
        evidence_count=result.evidence_count,
        fact_count=result.fact_count,
        entity_count=result.entity_count,
        wiki_page_count=result.wiki_page_count,
        edge_count=result.edge_count,
    )


def run_batch_pipeline(workspace_root: Path, doc_ids: list[str]) -> list[dict[str, object]]:
    return [asdict(run_document_pipeline(workspace_root, doc_id)) for doc_id in doc_ids]
