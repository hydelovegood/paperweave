from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from paperlab.enrich.forward_citations import (
    _get_paper,
    _resolve,
    select_papers_for_citations,
    track_forward_citations,
)


def _write_project_files(project_root: Path) -> None:
    prompts_dir = project_root / "configs" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (project_root / "configs" / "app.yaml").write_text(
        "\n".join([
            "database:",
            "  path: db/papers.db",
            "paths:",
            "  parsed_dir: data/parsed",
            "  cache_dir: data/cache",
            "  export_dir: data/exports",
            "  logs_dir: data/logs",
            "parsing:",
            "  prefer_deepxiv_for_arxiv: true",
            "  pymupdf_section_split: true",
            "llm:",
            "  summary_model: glm-5.1",
            "  qa_model: glm-5.1",
            "  lang: zh",
            "  max_retries: 2",
            "citations:",
            "  default_year_start: 2024",
            "  default_year_end: 2026",
            "  default_max_results: 30",
            "  download_oa_only: true",
            "export:",
            "  summary_file: data/exports/summary.md",
            "  qa_file: data/exports/QA.md",
        ]),
        encoding="utf-8",
    )

    for filename in (
        "summary_system_v1.txt",
        "summary_user_v1.txt",
        "qa_system_v1.txt",
        "qa_user_v1.txt",
    ):
        (prompts_dir / filename).write_text("placeholder", encoding="utf-8")


def _insert_classic_paper(db_path: Path, title="Classic Paper", doi=None, arxiv_id=None) -> int:
    now = "2026-04-10T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO papers (paper_uid, canonical_title, doi, arxiv_id, parse_status, enrich_status, summary_status, qa_status, graph_status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
            (f"paper-{uuid4()}", title, doi, arxiv_id, now, now),
        )
        paper_id = cursor.lastrowid
        conn.commit()
    return paper_id


def _sample_resolved():
    return {
        "openalex_id": "https://openalex.org/W12345",
        "doi": "10.1234/classic",
        "title": "Classic Paper",
        "year": 2023,
        "is_oa": True,
        "oa_url": "https://example.com/classic.pdf",
    }


def _sample_citations():
    return [
        {
            "openalex_id": "https://openalex.org/W11111",
            "doi": "10.1234/citing1",
            "title": "Citing Paper 1",
            "year": 2024,
            "is_oa": True,
            "oa_url": "https://example.com/citing1.pdf",
        },
        {
            "openalex_id": "https://openalex.org/W22222",
            "doi": "10.1234/citing2",
            "title": "Citing Paper 2",
            "year": 2025,
            "is_oa": False,
            "oa_url": None,
        },
    ]


# --- Paper selection test ---

def test_select_papers_for_citations_returns_eligible():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_classic_paper(db_path, "Eligible")
        _insert_classic_paper(db_path, "Already done")

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE papers SET citation_status = 'done' WHERE canonical_title = 'Already done'")
            conn.commit()

        ids = select_papers_for_citations(db_path)
        assert len(ids) == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


# --- Integration test with mocked APIs ---

def test_track_forward_citations_persists_edges_and_links(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        paper_id = _insert_classic_paper(db_path, doi="10.1234/classic")

        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.resolve_by_doi",
            lambda doi, mailto="": _sample_resolved(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *a, **kw: _sample_citations(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_arxiv",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_doi",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_title",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.crossref.resolve_by_doi",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.crossref.resolve_by_title",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.unpaywall.check_oa",
            lambda doi, email: None,
        )

        citing_ids = track_forward_citations(project_root, paper_id)

        assert len(citing_ids) == 2

        with sqlite3.connect(db_path) as conn:
            edges = conn.execute(
                "SELECT citing_paper_id, cited_paper_id, edge_source FROM citation_edges ORDER BY id"
            ).fetchall()
            links = conn.execute(
                "SELECT paper_id, link_type, is_open_access FROM external_links ORDER BY id"
            ).fetchall()
            paper = conn.execute(
                "SELECT enrich_status, citation_status, openalex_id FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()

        assert len(edges) == 2
        assert edges[0][1] == paper_id
        assert edges[0][2] == "openalex"

        # download_oa_only=true, only OA PDF is downloadable, but non-OA landing pages are still stored
        assert len(links) == 2
        assert links[0][1] == "oa_pdf"
        assert links[0][2] == 1
        assert links[1][1] == "landing_page"
        assert links[1][2] == 0

        assert paper == ("done", "done", "https://openalex.org/W12345")
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_track_forward_citations_normalizes_doi_landing_urls(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        paper_id = _insert_classic_paper(db_path, doi="https://doi.org/10.1234/classic")

        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.resolve_by_doi",
            lambda doi, mailto="": {
                "openalex_id": "https://openalex.org/W12345",
                "doi": "https://doi.org/10.1234/classic",
                "title": "Classic Paper",
                "year": 2023,
                "is_oa": False,
                "oa_url": None,
            },
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *a, **kw: [
                {
                    "doi": "https://doi.org/10.1234/citing1",
                    "title": "Citing Paper 1",
                    "year": 2024,
                    "is_oa": False,
                    "oa_url": None,
                }
            ],
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_arxiv",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_doi",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_title",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.crossref.resolve_by_doi",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.crossref.resolve_by_title",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.unpaywall.check_oa",
            lambda doi, email: None,
        )

        track_forward_citations(project_root, paper_id)

        with sqlite3.connect(db_path) as conn:
            url = conn.execute(
                "SELECT url FROM external_links ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]

        assert url == "https://doi.org/10.1234/citing1"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_track_citations_stores_non_oa_links_when_configured(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        # Override config to allow non-OA
        (project_root / "configs" / "app.yaml").write_text(
            "\n".join([
                "database:",
                "  path: db/papers.db",
                "paths:",
                "  parsed_dir: data/parsed",
                "  cache_dir: data/cache",
                "  export_dir: data/exports",
                "  logs_dir: data/logs",
                "parsing:",
                "  prefer_deepxiv_for_arxiv: true",
                "  pymupdf_section_split: true",
                "llm:",
                "  summary_model: glm-5.1",
                "  qa_model: glm-5.1",
                "  lang: zh",
                "  max_retries: 2",
                "citations:",
                "  default_year_start: 2024",
                "  default_year_end: 2026",
                "  default_max_results: 30",
                "  download_oa_only: false",
                "export:",
                "  summary_file: data/exports/summary.md",
                "  qa_file: data/exports/QA.md",
            ]),
            encoding="utf-8",
        )

        paper_id = _insert_classic_paper(db_path, doi="10.1234/classic")

        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.resolve_by_doi",
            lambda doi, mailto="": _sample_resolved(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *a, **kw: _sample_citations(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_arxiv",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_doi",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.resolve_by_title",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.crossref.resolve_by_doi",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.crossref.resolve_by_title",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.unpaywall.check_oa",
            lambda doi, email: None,
        )

        citing_ids = track_forward_citations(project_root, paper_id)

        with sqlite3.connect(db_path) as conn:
            links = conn.execute(
                "SELECT link_type, is_open_access FROM external_links ORDER BY id"
            ).fetchall()

        assert len(links) == 2
        assert links[0] == ("oa_pdf", 1)
        assert links[1] == ("landing_page", 0)
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_track_citations_deduplicates_by_doi(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        paper_id = _insert_classic_paper(db_path, doi="10.1234/classic")

        # Same citation returned twice (same DOI)
        dup_citations = [
            {"doi": "10.1234/dup", "title": "Dup", "year": 2024, "is_oa": True, "oa_url": "http://a.pdf"},
            {"doi": "10.1234/dup", "title": "Dup", "year": 2024, "is_oa": True, "oa_url": "http://a.pdf"},
        ]

        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.resolve_by_doi",
            lambda doi, mailto="": _sample_resolved(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *a, **kw: dup_citations,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.unpaywall.check_oa",
            lambda doi, email: None,
        )

        citing_ids = track_forward_citations(project_root, paper_id)

        assert len(citing_ids) == 2
        assert citing_ids[0] == citing_ids[1], "Same DOI should return same paper ID"

        with sqlite3.connect(db_path) as conn:
            paper_count = conn.execute("SELECT COUNT(*) FROM papers WHERE doi = '10.1234/dup'").fetchone()[0]
        assert paper_count == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_get_paper_returns_fields():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        pid = _insert_classic_paper(db_path, "Test Title", doi="10.1/t", arxiv_id="2501.00001")
        paper = _get_paper(db_path, pid)

        assert paper["title"] == "Test Title"
        assert paper["doi"] == "10.1/t"
        assert paper["arxiv_id"] == "2501.00001"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_track_forward_citations_uses_s2_paper_id_from_db(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, canonical_title, s2_paper_id, parse_status, enrich_status, summary_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (f"paper-{uuid4()}", "S2 Seed", "s2-seed-id", now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        seen: list[str] = []
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations._resolve",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.get_forward_citations",
            lambda s2_id, *a, **kw: seen.append(s2_id) or [],
        )

        citing_ids = track_forward_citations(project_root, paper_id)

        assert citing_ids == []
        assert seen == ["s2-seed-id"]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_track_forward_citations_records_failed_task_run(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.citations_cmd import citations_forward_cmd
        db_path = init_project(project_root)

        paper_id = _insert_classic_paper(db_path, doi="10.1234/classic")
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations._fetch_citations",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("api boom")),
        )

        citing_ids = citations_forward_cmd(project_root, paper_ids=[paper_id])
        assert citing_ids == []

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT citation_status FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()
            task = conn.execute(
                "SELECT status FROM task_runs WHERE task_name = 'citations' AND target_id = ? ORDER BY id DESC LIMIT 1",
                (str(paper_id),),
            ).fetchone()

        assert row[0] == "failed"
        assert task[0] == "failed"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_resolve_accumulates_ids_from_multiple_sources(monkeypatch):
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.openalex.resolve_by_doi",
        lambda doi, mailto="": {"openalex_id": "W1", "doi": "10.1/test"},
    )
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.openalex.resolve_by_title",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.s2.resolve_by_doi",
        lambda doi, api_key="": {"s2_id": "S2-1"},
    )
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.s2.resolve_by_arxiv",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.s2.resolve_by_title",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.crossref.resolve_by_doi",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "paperlab.enrich.forward_citations.crossref.resolve_by_title",
        lambda *args, **kwargs: None,
    )

    result = _resolve({"title": "T", "doi": "10.1/test", "arxiv_id": None}, "mail@example.com", "s2-key")

    assert result["openalex_id"] == "W1"
    assert result["s2_id"] == "S2-1"


def test_track_forward_citations_falls_back_to_s2_when_openalex_fetch_fails(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, canonical_title, openalex_id, s2_paper_id, parse_status, enrich_status, summary_status, qa_status, graph_status, citation_status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'done', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (f"paper-{uuid4()}", "Fallback Seed", "W-openalex", "S2-seed", now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        monkeypatch.setattr(
            "paperlab.enrich.forward_citations._resolve",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("openalex down")),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.s2.get_forward_citations",
            lambda *args, **kwargs: [{"title": "S2 Citing", "doi": "10.1/s2", "year": 2024, "is_oa": False, "oa_url": None}],
        )

        citing_ids = track_forward_citations(project_root, paper_id)

        assert len(citing_ids) == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_track_citations_deduplicates_without_doi_by_openalex_id(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        paper_id = _insert_classic_paper(db_path, doi="10.1234/classic")

        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.resolve_by_doi",
            lambda doi, mailto="": _sample_resolved(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *args, **kwargs: [
                {"openalex_id": "https://openalex.org/W99999", "title": "No DOI Paper", "year": 2024, "is_oa": False, "oa_url": None},
                {"openalex_id": "https://openalex.org/W99999", "title": "No DOI Paper", "year": 2024, "is_oa": False, "oa_url": None},
            ],
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.unpaywall.check_oa",
            lambda doi, email: None,
        )

        citing_ids = track_forward_citations(project_root, paper_id)

        assert len(citing_ids) == 2
        assert citing_ids[0] == citing_ids[1]

        with sqlite3.connect(db_path) as conn:
            paper_count = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE openalex_id = 'https://openalex.org/W99999'"
            ).fetchone()[0]
        assert paper_count == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
