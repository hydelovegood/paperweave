from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CanonicalSection:
    name: str
    text: str
    order: int


@dataclass(frozen=True, slots=True)
class CanonicalPaper:
    source: str
    paper_id: str
    title: str
    authors: list[dict[str, str]]
    abstract: str
    year: int | None
    venue: str
    doi: str | None
    arxiv_id: str | None
    sections: list[CanonicalSection]
    references_raw: list[str]
    full_text: str
    parse_quality: float | None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["sections"] = [asdict(section) for section in self.sections]
        return payload
