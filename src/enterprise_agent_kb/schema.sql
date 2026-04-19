CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_type TEXT NOT NULL,
    mime_type TEXT,
    sha256 TEXT NOT NULL,
    file_size INTEGER,
    page_count INTEGER,
    language TEXT,
    version_label TEXT,
    source_path TEXT NOT NULL,
    ingest_time TEXT NOT NULL,
    update_time TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pages (
    page_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    page_no INTEGER NOT NULL,
    width REAL,
    height REAL,
    parser_confidence REAL,
    ocr_confidence REAL,
    risk_level TEXT NOT NULL,
    page_status TEXT NOT NULL,
    screenshot_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocks (
    block_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    block_type TEXT NOT NULL,
    reading_order INTEGER,
    text_content TEXT,
    raw_text TEXT,
    bbox_json TEXT,
    parser_confidence REAL,
    ocr_confidence REAL,
    risk_flags_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    block_type TEXT NOT NULL,
    raw_text TEXT,
    normalized_text TEXT,
    image_ref TEXT,
    table_ref TEXT,
    page_no INTEGER NOT NULL,
    confidence REAL,
    risk_level TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    alias_json TEXT,
    description TEXT,
    source_confidence REAL,
    entity_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    fact_type TEXT NOT NULL,
    subject_entity_id TEXT,
    predicate TEXT NOT NULL,
    object_value TEXT,
    object_entity_id TEXT,
    qualifiers_json TEXT,
    confidence REAL,
    fact_status TEXT NOT NULL,
    source_doc_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_evidence_map (
    fact_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    support_type TEXT NOT NULL,
    PRIMARY KEY (fact_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    src_entity_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    dst_entity_id TEXT NOT NULL,
    version_scope TEXT,
    condition_scope TEXT,
    confidence REAL,
    edge_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edge_evidence_map (
    edge_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (edge_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS wiki_pages (
    page_id TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    entity_id TEXT,
    source_fact_ids_json TEXT,
    source_doc_ids_json TEXT,
    trust_status TEXT NOT NULL,
    file_path TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_reports (
    doc_id TEXT PRIMARY KEY,
    overall_score REAL,
    ocr_avg_confidence REAL,
    structure_score REAL,
    table_score REAL,
    fact_alignment_score REAL,
    conflict_count INTEGER,
    high_risk_page_count INTEGER,
    review_required_count INTEGER,
    blocked_count INTEGER,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    payload_json TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    upstream_type TEXT NOT NULL,
    upstream_id TEXT NOT NULL,
    downstream_type TEXT NOT NULL,
    downstream_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    PRIMARY KEY (upstream_type, upstream_id, downstream_type, downstream_id)
);

CREATE TABLE IF NOT EXISTS system_counters (
    counter_key TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_blocks_doc_id ON blocks(doc_id);
CREATE INDEX IF NOT EXISTS idx_blocks_page_id ON blocks(page_id);
CREATE INDEX IF NOT EXISTS idx_evidence_doc_id ON evidence(doc_id);
CREATE INDEX IF NOT EXISTS idx_evidence_page_id ON evidence(page_id);
CREATE INDEX IF NOT EXISTS idx_facts_source_doc_id ON facts(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_jobs_target ON jobs(target_type, target_id, status);
CREATE INDEX IF NOT EXISTS idx_dependencies_upstream ON dependencies(upstream_type, upstream_id);
CREATE INDEX IF NOT EXISTS idx_dependencies_downstream ON dependencies(downstream_type, downstream_id);
