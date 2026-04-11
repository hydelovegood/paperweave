from __future__ import annotations

import json
import re
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from paperlab.config import load_settings
from paperlab.parsing.canonical import CanonicalPaper
from paperlab.parsing.deepxiv_parser import (
    DeepXivRecoverableError,
    parse_arxiv_paper,
    search_arxiv_paper,
)
from paperlab.parsing.pymupdf_parser import parse_pdf


ARXIV_ID_RE = re.compile(r"arXiv:?\s*(\d{4}\.\d{4,5})", re.IGNORECASE)


def extract_arxiv_id(text: str) -> str | None:
    match = ARXIV_ID_RE.search(text)
    return match.group(1) if match else None


def read_pdf_text(pdf_path: Path | str) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed") from exc

    document = fitz.open(Path(pdf_path).expanduser().resolve())
    text = "".join(page.get_text() for page in document)
    document.close()
    return text


def read_pdf_head_text(pdf_path: Path | str, max_pages: int = 2) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed") from exc

    document = fitz.open(Path(pdf_path).expanduser().resolve())
    text = "".join(document[index].get_text() for index in range(min(max_pages, len(document))))
    document.close()
    return text


def parse_document(
    input_path: Path | str,
    deepxiv_token: str | None = None,
) -> CanonicalPaper:
    candidate = str(input_path).strip()
    direct_id = _extract_direct_arxiv_id(candidate)
    if direct_id:
        return parse_arxiv_paper(direct_id, token=deepxiv_token)

    resolved_path = Path(candidate).expanduser()
    if resolved_path.suffix.lower() == ".pdf":
        resolved_path = resolved_path.resolve()
        text = read_pdf_head_text(resolved_path)
        arxiv_id = extract_arxiv_id(text)

        if arxiv_id:
            try:
                return parse_arxiv_paper(arxiv_id, token=deepxiv_token)
            except DeepXivRecoverableError:
                return parse_pdf(resolved_path)

        return parse_pdf(resolved_path)

    if not resolved_path.exists():
        arxiv_id = search_arxiv_paper(candidate, token=deepxiv_token)
        if arxiv_id is None:
            raise FileNotFoundError(f"No local file or DeepXiv search result for: {candidate}")
        return parse_arxiv_paper(arxiv_id, token=deepxiv_token)

    resolved_path = resolved_path.resolve()
    text = read_pdf_text(resolved_path)
    arxiv_id = extract_arxiv_id(text)

    if arxiv_id:
        try:
            return parse_arxiv_paper(arxiv_id, token=deepxiv_token)
        except DeepXivRecoverableError:
            return parse_pdf(resolved_path)

    return parse_pdf(resolved_path)


def _extract_direct_arxiv_id(value: str) -> str | None:
    direct_match = re.fullmatch(r"\d{4}\.\d{4,5}", value)
    return direct_match.group(0) if direct_match else None


def parse_and_persist(
    project_root: Path | str,
    paper_id: int,
    input_path: Path | str,
    deepxiv_token: str | None = None,
) -> CanonicalPaper:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    canonical = parse_document(
        input_path=input_path,
        deepxiv_token=deepxiv_token or settings.secrets.deepxiv_token,
    )

    parsed_dir = (root / settings.paths.parsed_dir).resolve()
    parsed_dir.mkdir(parents=True, exist_ok=True)
    parsed_json_path = parsed_dir / f"{paper_id}.json"
    parsed_json_path.write_text(
        json.dumps(canonical.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    db_path = (root / settings.database.path).resolve()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM sections WHERE paper_id = ?", (paper_id,))
        for section in canonical.sections:
            connection.execute(
                """
                INSERT INTO sections (paper_id, section_order, section_name, section_type, text_content, token_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    section.order,
                    section.name,
                    None,
                    section.text,
                    None,
                ),
            )

        connection.execute(
            """
            UPDATE papers
            SET canonical_title = ?,
                abstract = ?,
                arxiv_id = ?,
                year = ?,
                venue = ?,
                doi = ?,
                parse_quality = ?,
                parse_status = 'done',
                updated_at = ?
            WHERE id = ?
            """,
            (
                canonical.title,
                canonical.abstract,
                canonical.arxiv_id,
                canonical.year,
                canonical.venue,
                canonical.doi,
                canonical.parse_quality,
                now,
                paper_id,
            ),
        )
        connection.commit()

    return canonical
