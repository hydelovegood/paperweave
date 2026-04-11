from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from paperlab.parsing.canonical import CanonicalPaper, CanonicalSection


SECTION_RE = re.compile(
    r"^(\d*\.?\d*\s+"
    r"(?:Abstract|Introduction|Background|Method|Related\s+Work|Conclusion|"
    r"Discussion|Appendix|References|Acknowledgment|Preliminaries|Experiments|Results)|"
    r"Appendix\s+[A-Z])",
    re.IGNORECASE,
)


def parse_pdf(pdf_path: Path | str) -> CanonicalPaper:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed") from exc

    resolved_path = Path(pdf_path).expanduser().resolve()
    document = fitz.open(resolved_path)
    full_text = "".join(page.get_text() for page in document)
    metadata = {key: value for key, value in document.metadata.items() if value}

    elements: list[str] = []
    for page in document:
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            text = "".join(
                span["text"] for line in block["lines"] for span in line["spans"]
            ).strip()
            if text:
                elements.append(text)
    document.close()

    sections = _split_sections(elements)
    return CanonicalPaper(
        source="pymupdf",
        paper_id=f"paper-{uuid4()}",
        title=metadata.get("title", resolved_path.stem),
        authors=[
            {"name": author.strip()}
            for author in metadata.get("author", "").split(";")
            if author.strip()
        ],
        abstract=_extract_abstract(elements),
        year=None,
        venue="",
        doi=None,
        arxiv_id=_extract_arxiv_id(full_text),
        sections=sections,
        references_raw=[],
        full_text=full_text.strip(),
        parse_quality=0.7,
    )


def _extract_arxiv_id(text: str) -> str | None:
    match = re.search(r"arXiv:?\s*(\d{4}\.\d{4,5})", text)
    return match.group(1) if match else None


def _extract_abstract(elements: list[str]) -> str:
    for index, text in enumerate(elements):
        if re.match(r"^abstract$", text.strip(), re.IGNORECASE):
            parts: list[str] = []
            for next_text in elements[index + 1 :]:
                if SECTION_RE.match(next_text.strip()):
                    break
                parts.append(next_text)
            return " ".join(parts).strip()
    return ""


def _split_sections(elements: list[str]) -> list[CanonicalSection]:
    sections: list[CanonicalSection] = []
    current_name = "Heading"
    current_lines: list[str] = []

    def flush(section_name: str, lines: list[str], order: int) -> None:
        if not lines:
            return
        sections.append(
            CanonicalSection(
                name=section_name,
                text="\n".join(lines).strip(),
                order=order,
            )
        )

    order = 1
    for text in elements:
        if SECTION_RE.match(text.strip()):
            flush(current_name, current_lines, order)
            if current_lines:
                order += 1
            current_name = text.strip()
            current_lines = []
        else:
            current_lines.append(text)

    flush(current_name, current_lines, order)
    return sections
