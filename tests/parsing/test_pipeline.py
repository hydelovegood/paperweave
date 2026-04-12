from __future__ import annotations

import json
import sqlite3
import shutil
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest

from paperlab.parsing.canonical import CanonicalPaper, CanonicalSection
from paperlab.parsing.deepxiv_parser import DeepXivRecoverableError


def _sample_paper(source: str, arxiv_id: str | None = None) -> CanonicalPaper:
    return CanonicalPaper(
        source=source,
        paper_id="paper-test",
        title="Sample Title",
        authors=[{"name": "Alice"}],
        abstract="Sample abstract",
        year=2025,
        venue="arXiv",
        doi=None,
        arxiv_id=arxiv_id,
        sections=[
            CanonicalSection(name="Introduction", text="Intro text", order=1),
            CanonicalSection(name="Method", text="Method text", order=2),
        ],
        references_raw=["Ref A"],
        full_text="Intro text\nMethod text",
        parse_quality=0.95,
    )


def test_parse_document_routes_arxiv_pdf_to_deepxiv(monkeypatch) -> None:
    calls: list[str] = []

    def fake_read_pdf_head_text(_path, max_pages=2):
        return "This paper is on arXiv:2501.12345 and has structured text."

    def fake_deepxiv(arxiv_id: str, token: str | None = None):
        calls.append(f"deepxiv:{arxiv_id}:{token}")
        return _sample_paper(source="deepxiv", arxiv_id=arxiv_id)

    def fail_pymupdf(_path):
        raise AssertionError("PyMuPDF fallback should not be used when DeepXiv succeeds")

    monkeypatch.setattr("paperlab.parsing.pipeline.read_pdf_head_text", fake_read_pdf_head_text)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_arxiv_paper", fake_deepxiv)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_pdf", fail_pymupdf)

    from paperlab.parsing.pipeline import parse_document

    result = parse_document("dummy.pdf", deepxiv_token="token-123")

    assert result.source == "deepxiv"
    assert result.arxiv_id == "2501.12345"
    assert calls == ["deepxiv:2501.12345:token-123"]


def test_parse_document_falls_back_to_pymupdf_when_deepxiv_fails(monkeypatch) -> None:
    def fake_read_pdf_head_text(_path, max_pages=2):
        return "arXiv:2502.54321"

    def fail_deepxiv(_arxiv_id: str, token: str | None = None):
        raise DeepXivRecoverableError("DeepXiv unavailable")

    def fake_pymupdf(_path):
        return _sample_paper(source="pymupdf")

    monkeypatch.setattr("paperlab.parsing.pipeline.read_pdf_head_text", fake_read_pdf_head_text)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_arxiv_paper", fail_deepxiv)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_pdf", fake_pymupdf)

    from paperlab.parsing.pipeline import parse_document

    result = parse_document("dummy.pdf", deepxiv_token="token-123")

    assert result.source == "pymupdf"
    assert result.title == "Sample Title"


def test_canonical_paper_normalizes_to_expected_shape() -> None:
    paper = _sample_paper(source="deepxiv", arxiv_id="2501.12345")

    payload = paper.to_dict()

    assert payload["paper_id"] == "paper-test"
    assert payload["title"] == "Sample Title"
    assert payload["sections"] == [
        {"name": "Introduction", "text": "Intro text", "order": 1},
        {"name": "Method", "text": "Method text", "order": 2},
    ]
    assert payload["references_raw"] == ["Ref A"]
    assert payload["parse_quality"] == 0.95


def _write_project_files(project_root: Path) -> None:
    prompts_dir = project_root / "configs" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (project_root / "configs" / "app.yaml").write_text(
        "\n".join(
            [
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
                "  summary_model: gpt-5.4",
                "  qa_model: gpt-5.4",
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
            ]
        ),
        encoding="utf-8",
    )

    for filename in (
        "summary_system_v1.txt",
        "summary_user_v1.txt",
        "qa_system_v1.txt",
        "qa_user_v1.txt",
    ):
        (prompts_dir / filename).write_text("placeholder", encoding="utf-8")


def test_parse_document_uses_deepxiv_search_for_plain_query(monkeypatch) -> None:
    calls: list[str] = []

    def fake_search(query: str, token: str | None = None):
        calls.append(f"search:{query}:{token}")
        return "2503.11111"

    def fake_parse(arxiv_id: str, token: str | None = None):
        calls.append(f"parse:{arxiv_id}:{token}")
        return _sample_paper(source="deepxiv", arxiv_id=arxiv_id)

    monkeypatch.setattr("paperlab.parsing.pipeline.search_arxiv_paper", fake_search)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_arxiv_paper", fake_parse)

    from paperlab.parsing.pipeline import parse_document

    result = parse_document("batch size invariance", deepxiv_token="token-xyz")

    assert result.arxiv_id == "2503.11111"
    assert calls == [
        "search:batch size invariance:token-xyz",
        "parse:2503.11111:token-xyz",
    ]


def test_parse_and_persist_writes_sections_and_parsed_json(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.parsing.pipeline import parse_and_persist

        db_path = init_project(project_root)
        now = "2026-04-10T00:00:00+00:00"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO papers (
                    paper_uid,
                    parse_status,
                    enrich_status,
                    summary_status,
                    qa_status,
                    graph_status,
                    created_at,
                    updated_at
                )
                VALUES (?, 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)
                """,
                ("paper-123", now, now),
            )
            paper_row_id = cursor.lastrowid
            conn.commit()

        monkeypatch.setattr(
            "paperlab.parsing.pipeline.parse_document",
            lambda input_path, deepxiv_token=None: _sample_paper(
                source="deepxiv",
                arxiv_id="2501.12345",
            ),
        )
        monkeypatch.setattr(
            "paperlab.enrich.biomed_pre_enrich.pre_enrich_biomed_metadata",
            lambda *args, **kwargs: None,
        )

        canonical = parse_and_persist(
            project_root=project_root,
            paper_id=paper_row_id,
            input_path="anything.pdf",
        )

        parsed_json_path = project_root / "data" / "parsed" / f"{paper_row_id}.json"
        assert parsed_json_path.exists()
        assert canonical.title == "Sample Title"

        payload = json.loads(parsed_json_path.read_text(encoding="utf-8"))
        assert payload["title"] == "Sample Title"
        assert len(payload["sections"]) == 2

        with sqlite3.connect(db_path) as conn:
            section_rows = conn.execute(
                "SELECT section_name, text_content, section_order FROM sections WHERE paper_id = ? ORDER BY section_order",
                (paper_row_id,),
            ).fetchall()
            paper_rows = conn.execute(
                "SELECT canonical_title, abstract, arxiv_id, year, venue, doi, parse_quality, parse_status FROM papers WHERE id = ?",
                (paper_row_id,),
            ).fetchall()

        assert section_rows == [
            ("Introduction", "Intro text", 1),
            ("Method", "Method text", 2),
        ]
        assert paper_rows == [("Sample Title", "Sample abstract", "2501.12345", 2025, "arXiv", None, 0.95, "done")]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_parse_and_persist_pre_enriches_biomed_metadata_and_uses_pmc(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.parsing.pipeline import parse_and_persist

        db_path = init_project(project_root)
        now = "2026-04-10T00:00:00+00:00"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO papers (
                    paper_uid,
                    parse_status,
                    enrich_status,
                    summary_status,
                    qa_status,
                    graph_status,
                    citation_status,
                    created_at,
                    updated_at
                )
                VALUES (?, 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)
                """,
                ("paper-biomed", now, now),
            )
            paper_row_id = cursor.lastrowid
            conn.commit()

        monkeypatch.setattr(
            "paperlab.parsing.pipeline.read_pdf_head_text",
            lambda _path, max_pages=2: "Nature Medicine\nhttps://doi.org/10.1038/s41591-026-04247-3",
        )
        monkeypatch.setattr(
            "paperlab.enrich.biomed_pre_enrich.read_pdf_head_text",
            lambda _path, max_pages=2: "Nature Medicine\nhttps://doi.org/10.1038/s41591-026-04247-3",
        )
        monkeypatch.setattr(
            "paperlab.enrich.pubmed_client.resolve_by_doi",
            lambda doi, api_key='': {
                "pmid": "41862772",
                "pmcid": "PMC1234567",
                "doi": "10.1038/s41591-026-04247-3",
                "journal": "Nature Medicine",
                "publication_type": "Journal Article",
                "mesh_terms": ["Heart Failure", "Smartwatch"],
                "title": "Remote monitoring of heart failure exacerbations using a smartwatch",
            },
        )
        monkeypatch.setattr(
            "paperlab.enrich.pmc_client.fetch_fulltext_xml",
            lambda pmcid: "<article></article>",
        )
        monkeypatch.setattr(
            "paperlab.enrich.pmc_client.parse_jats_xml",
            lambda xml_text: CanonicalPaper(
                source="pmc",
                paper_id="pmc-paper",
                title="Remote monitoring of heart failure exacerbations using a smartwatch",
                authors=[{"name": "Author"}],
                abstract="Structured abstract",
                year=2026,
                venue="Nature Medicine",
                doi="10.1038/s41591-026-04247-3",
                arxiv_id=None,
                sections=[CanonicalSection(name="Introduction", text="Intro", order=1)],
                references_raw=[],
                full_text="Intro",
                parse_quality=1.0,
            ),
        )

        canonical = parse_and_persist(
            project_root=project_root,
            paper_id=paper_row_id,
            input_path="biomed.pdf",
        )

        assert canonical.source == "pmc"

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT pmid, pmcid, journal, publication_type, mesh_terms, parse_status FROM papers WHERE id = ?",
                (paper_row_id,),
            ).fetchone()

        assert row[0] == "41862772"
        assert row[1] == "PMC1234567"
        assert row[2] == "Nature Medicine"
        assert row[3] == "Journal Article"
        assert json.loads(row[4]) == ["Heart Failure", "Smartwatch"]
        assert row[5] == "done"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_parse_document_does_not_hide_unexpected_deepxiv_errors(monkeypatch) -> None:
    def fake_read_pdf_head_text(_path, max_pages=2):
        return "arXiv:2504.00001"

    def unexpected_deepxiv_bug(_arxiv_id: str, token: str | None = None):
        raise ValueError("unexpected parser bug")

    def fail_pymupdf(_path):
        raise AssertionError("PyMuPDF fallback should not run on unexpected DeepXiv bugs")

    monkeypatch.setattr("paperlab.parsing.pipeline.read_pdf_head_text", fake_read_pdf_head_text)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_arxiv_paper", unexpected_deepxiv_bug)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_pdf", fail_pymupdf)

    from paperlab.parsing.pipeline import parse_document

    with pytest.raises(ValueError, match="unexpected parser bug"):
        parse_document("dummy.pdf", deepxiv_token="token-123")


def test_parse_arxiv_paper_ignores_unmatched_list_entries(monkeypatch) -> None:
    class FakeReader:
        def __init__(self, token=None):
            self.token = token

        def head(self, arxiv_id):
            return {
                "title": "Phasic Policy Gradient",
                "abstract": "Abstract",
                "authors": [{"name": "Author"}],
                "year": 2020,
                "venue": "arXiv",
                "doi": None,
            }

        def json(self, arxiv_id):
            return {
                "arxiv_id": arxiv_id,
                "data": {
                    "heading": {"content": "Heading"},
                    "Introduction": {"content": "Intro"},
                    "Method": {"content": "Method"},
                    "unmatched": [{"content": "Loose fragment"}],
                },
            }

    fake_sdk = types.SimpleNamespace(
        APIError=RuntimeError,
        NotFoundError=RuntimeError,
        Reader=FakeReader,
    )
    monkeypatch.setitem(sys.modules, "deepxiv_sdk", fake_sdk)

    from paperlab.parsing.deepxiv_parser import parse_arxiv_paper

    paper = parse_arxiv_paper("2009.04416", token="dummy-token")

    assert paper.title == "Phasic Policy Gradient"
    assert [section.name for section in paper.sections] == ["Introduction", "Method"]
    assert "Loose fragment" not in paper.full_text


def test_parse_document_does_not_use_reference_arxiv_id_from_late_pages(monkeypatch) -> None:
    def fake_head_text(_path, max_pages=2):
        return "On the Spectral Bias of Neural Networks\\nNo arXiv id on the front page."

    def fail_deepxiv(*args, **kwargs):
        raise AssertionError("DeepXiv should not run when only reference sections contain arXiv IDs")

    def fake_pymupdf(_path):
        return _sample_paper(source="pymupdf")

    monkeypatch.setattr("paperlab.parsing.pipeline.read_pdf_head_text", fake_head_text)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_arxiv_paper", fail_deepxiv)
    monkeypatch.setattr("paperlab.parsing.pipeline.parse_pdf", fake_pymupdf)

    from paperlab.parsing.pipeline import parse_document

    result = parse_document("dummy.pdf", deepxiv_token="token-123")

    assert result.source == "pymupdf"


def test_parse_and_persist_continues_when_biomed_pre_enrich_lookup_fails(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.parsing.pipeline import parse_and_persist
        import requests

        db_path = init_project(project_root)
        now = "2026-04-10T00:00:00+00:00"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO papers (
                    paper_uid,
                    parse_status,
                    enrich_status,
                    summary_status,
                    qa_status,
                    graph_status,
                    citation_status,
                    created_at,
                    updated_at
                )
                VALUES (?, 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)
                """,
                ("paper-pre-enrich-fail", now, now),
            )
            paper_row_id = cursor.lastrowid
            conn.commit()

        monkeypatch.setattr(
            "paperlab.enrich.biomed_pre_enrich.read_pdf_head_text",
            lambda _path, max_pages=2: "Nature Medicine\n10.1038/test",
        )
        monkeypatch.setattr(
            "paperlab.enrich.biomed_pre_enrich.extract_doi",
            lambda text: "10.1038/test",
        )
        monkeypatch.setattr(
            "paperlab.enrich.pubmed_client.resolve_by_doi",
            lambda *args, **kwargs: (_ for _ in ()).throw(requests.RequestException("pubmed down")),
        )
        monkeypatch.setattr(
            "paperlab.parsing.pipeline.parse_document",
            lambda input_path, deepxiv_token=None: _sample_paper(source="pymupdf"),
        )

        canonical = parse_and_persist(project_root, paper_row_id, "anything.pdf")

        assert canonical.source == "pymupdf"
        with sqlite3.connect(db_path) as conn:
            status = conn.execute(
                "SELECT parse_status FROM papers WHERE id = ?",
                (paper_row_id,),
            ).fetchone()[0]
        assert status == "done"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
