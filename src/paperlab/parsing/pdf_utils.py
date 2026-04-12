from __future__ import annotations

import re
from pathlib import Path

ARXIV_ID_RE = re.compile(r"arXiv:?\s*(\d{4}\.\d{4,5})", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.IGNORECASE)


def extract_arxiv_id(text: str) -> str | None:
    match = ARXIV_ID_RE.search(text)
    return match.group(1) if match else None


def extract_doi(text: str) -> str | None:
    match = DOI_RE.search(text)
    if not match:
        return None
    return match.group(1).rstrip(".,);]")


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
