from __future__ import annotations

from uuid import uuid4

from paperlab.parsing.canonical import CanonicalPaper, CanonicalSection


class DeepXivRecoverableError(RuntimeError):
    """Raised when the caller can safely fall back from DeepXiv."""


def parse_arxiv_paper(arxiv_id: str, token: str | None = None) -> CanonicalPaper:
    try:
        from deepxiv_sdk import APIError, NotFoundError, Reader
    except ImportError as exc:
        raise DeepXivRecoverableError("deepxiv_sdk is not installed") from exc

    reader = Reader(token=token)
    try:
        head = reader.head(arxiv_id)
        full = reader.json(arxiv_id)
    except (APIError, NotFoundError) as exc:
        raise DeepXivRecoverableError(str(exc)) from exc

    sections: list[CanonicalSection] = []
    references_raw: list[str] = []

    for order, (name, section_payload) in enumerate(full["data"].items(), start=1):
        if name == "heading":
            continue
        if not isinstance(section_payload, dict):
            continue
        content = section_payload.get("content", "")
        sections.append(CanonicalSection(name=name, text=content, order=order))

    return CanonicalPaper(
        source="deepxiv",
        paper_id=f"paper-{uuid4()}",
        title=head.get("title", ""),
        authors=head.get("authors", []),
        abstract=head.get("abstract", ""),
        year=head.get("year"),
        venue=head.get("venue", ""),
        doi=head.get("doi"),
        arxiv_id=arxiv_id,
        sections=sections,
        references_raw=references_raw,
        full_text="\n\n".join(
            [full["data"].get("heading", {}).get("content", "")]
            + [section.text for section in sections]
        ).strip(),
        parse_quality=1.0,
    )


def search_arxiv_paper(query: str, token: str | None = None) -> str | None:
    try:
        from deepxiv_sdk import APIError, Reader
    except ImportError as exc:
        raise DeepXivRecoverableError("deepxiv_sdk is not installed") from exc

    reader = Reader(token=token)
    try:
        result = reader.search(query, size=1)
    except APIError as exc:
        raise DeepXivRecoverableError(str(exc)) from exc
    if result.get("results"):
        return result["results"][0].get("arxiv_id")
    return None
