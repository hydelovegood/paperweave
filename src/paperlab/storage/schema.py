from __future__ import annotations

import sqlite3


CORE_TABLE_NAMES = (
    "files",
    "papers",
    "paper_files",
    "sections",
    "summaries",
    "qa_items",
    "citation_edges",
    "external_links",
    "task_runs",
)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sha256 TEXT NOT NULL UNIQUE,
        path TEXT NOT NULL UNIQUE,
        filename TEXT NOT NULL,
        size_bytes INTEGER,
        mtime_utc TEXT,
        imported_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS papers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_uid TEXT NOT NULL UNIQUE,
        canonical_title TEXT,
        normalized_title TEXT,
        year INTEGER,
        venue TEXT,
        abstract TEXT,
        doi TEXT,
        arxiv_id TEXT,
        openalex_id TEXT,
        s2_paper_id TEXT,
        parse_quality REAL,
        language TEXT DEFAULT 'en',
        parse_status TEXT DEFAULT 'pending',
        enrich_status TEXT DEFAULT 'pending',
        summary_status TEXT DEFAULT 'pending',
        qa_status TEXT DEFAULT 'pending',
        graph_status TEXT DEFAULT 'pending',
        citation_status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_files (
        paper_id INTEGER NOT NULL,
        file_id INTEGER NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (paper_id, file_id),
        FOREIGN KEY (paper_id) REFERENCES papers(id),
        FOREIGN KEY (file_id) REFERENCES files(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        section_order INTEGER,
        section_name TEXT,
        section_type TEXT,
        text_content TEXT,
        token_count INTEGER,
        FOREIGN KEY (paper_id) REFERENCES papers(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        version TEXT NOT NULL,
        lang TEXT NOT NULL DEFAULT 'zh',
        model_name TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        summary_md TEXT NOT NULL,
        evidence_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (paper_id) REFERENCES papers(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qa_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        version TEXT NOT NULL DEFAULT 'v1',
        qa_type TEXT NOT NULL,
        category TEXT,
        depth_level INTEGER DEFAULT 2,
        question TEXT NOT NULL,
        answer_text TEXT NOT NULL,
        answer_mode TEXT,
        evidence_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (paper_id) REFERENCES papers(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS citation_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citing_paper_id INTEGER NOT NULL,
        cited_paper_id INTEGER NOT NULL,
        edge_source TEXT NOT NULL,
        edge_type TEXT NOT NULL DEFAULT 'cites',
        confidence REAL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        UNIQUE (citing_paper_id, cited_paper_id, edge_source),
        FOREIGN KEY (citing_paper_id) REFERENCES papers(id),
        FOREIGN KEY (cited_paper_id) REFERENCES papers(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        link_type TEXT NOT NULL,
        url TEXT NOT NULL,
        source TEXT NOT NULL,
        is_open_access INTEGER DEFAULT 0,
        is_downloaded INTEGER DEFAULT 0,
        local_path TEXT,
        checked_at TEXT,
        UNIQUE (paper_id, url),
        FOREIGN KEY (paper_id) REFERENCES papers(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT,
        model_name TEXT,
        status TEXT NOT NULL,
        input_hash TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        log_path TEXT
    )
    """,
)


def create_all_tables(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    _ensure_papers_columns(connection)
    connection.commit()


def _ensure_papers_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(papers)").fetchall()
    }
    if "parse_quality" not in columns:
        connection.execute("ALTER TABLE papers ADD COLUMN parse_quality REAL")
    if "citation_status" not in columns:
        connection.execute("ALTER TABLE papers ADD COLUMN citation_status TEXT DEFAULT 'pending'")

    qa_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(qa_items)").fetchall()
    }
    if "version" not in qa_columns:
        connection.execute("ALTER TABLE qa_items ADD COLUMN version TEXT NOT NULL DEFAULT 'v1'")
