from __future__ import annotations

import xml.etree.ElementTree as ET
from uuid import uuid4

from paperlab.enrich.http import get_json
from paperlab.parsing.canonical import CanonicalPaper, CanonicalSection

_EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def fetch_fulltext_xml(pmcid: str) -> str | None:
    """Fetch JATS full-text XML from Europe PMC. PMCID should be like 'PMC1234567'."""
    if not pmcid:
        return None
    resp = get_json(
        f"{_EPMC_BASE}/{pmcid}/fullTextXML",
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def parse_jats_xml(xml_text: str) -> CanonicalPaper | None:
    """Parse JATS XML into CanonicalPaper."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    article = root.find(".//article")
    if article is None:
        # Some XML wraps in <response> or other containers
        article = root

    meta = _extract_meta(article)
    sections = _extract_sections(article)
    abstract = _extract_abstract(article)
    full_text = "\n\n".join(s.text for s in sections if s.text)
    authors = _extract_authors(article)
    refs = _extract_references(article)

    return CanonicalPaper(
        source="pmc",
        paper_id=f"paper-{uuid4()}",
        title=meta.get("title", ""),
        authors=authors,
        abstract=abstract,
        year=meta.get("year"),
        venue=meta.get("journal", ""),
        doi=meta.get("doi"),
        arxiv_id=meta.get("arxiv_id"),
        sections=sections,
        references_raw=refs,
        full_text=full_text.strip(),
        parse_quality=1.0,
    )


def _extract_meta(article: ET.Element) -> dict:
    result: dict = {}

    title_el = article.find(".//article-title")
    if title_el is not None:
        result["title"] = "".join(title_el.itertext()).strip()

    journal_el = article.find(".//journal-title")
    if journal_el is not None:
        result["journal"] = journal_el.text or ""

    year_el = article.find(".//pub-date/year")
    if year_el is not None and year_el.text:
        try:
            result["year"] = int(year_el.text)
        except ValueError:
            pass

    for article_id in article.findall(".//article-id"):
        id_type = article_id.get("pub-id-type", "")
        if id_type == "doi":
            result["doi"] = article_id.text
        elif id_type == "arxiv":
            result["arxiv_id"] = article_id.text

    return result


def _extract_abstract(article: ET.Element) -> str:
    abstract_el = article.find(".//abstract")
    if abstract_el is None:
        return ""

    # Structured abstract with labeled sections
    parts = []
    for sec in abstract_el.findall(".//sec"):
        title_el = sec.find("title")
        body_el = sec.find("p")
        if body_el is not None:
            text = "".join(body_el.itertext()).strip()
            if title_el is not None:
                label = "".join(title_el.itertext()).strip()
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)

    # Unstructured abstract (single <p> or multiple <p>)
    if not parts:
        for p in abstract_el.findall(".//p"):
            text = "".join(p.itertext()).strip()
            if text:
                parts.append(text)

    return "\n".join(parts)


def _extract_sections(article: ET.Element) -> list[CanonicalSection]:
    body = article.find(".//body")
    if body is None:
        return []

    sections: list[CanonicalSection] = []
    order = 1

    for sec in body.findall(".//sec"):
        title_el = sec.find("title")
        name = "".join(title_el.itertext()).strip() if title_el is not None else f"Section {order}"

        paragraphs = []
        for p in sec.findall("p"):
            text = "".join(p.itertext()).strip()
            if text:
                paragraphs.append(text)

        # Include subsections as part of the parent section text
        for subsec in sec.findall("sec"):
            sub_title_el = subsec.find("title")
            if sub_title_el is not None:
                paragraphs.append("## " + "".join(sub_title_el.itertext()).strip())
            for p in subsec.findall("p"):
                text = "".join(p.itertext()).strip()
                if text:
                    paragraphs.append(text)

        if paragraphs:
            sections.append(
                CanonicalSection(name=name, text="\n\n".join(paragraphs), order=order)
            )
            order += 1

    return sections


def _extract_authors(article: ET.Element) -> list[dict]:
    authors = []
    for contrib in article.findall(".//contrib-group/contrib"):
        name_el = contrib.find("name")
        if name_el is None:
            collab = contrib.find("collab")
            if collab is not None:
                authors.append({"name": "".join(collab.itertext()).strip()})
            continue
        surname = name_el.find("surname")
        given = name_el.find("given-names")
        parts = []
        if given is not None and given.text:
            parts.append(given.text)
        if surname is not None and surname.text:
            parts.append(surname.text)
        if parts:
            authors.append({"name": " ".join(parts)})
    return authors


def _extract_references(article: ET.Element) -> list[str]:
    refs = []
    for ref in article.findall(".//ref-list/ref"):
        parts = []
        for cit_title in ref.findall(".//article-title"):
            parts.append("".join(cit_title.itertext()).strip())
        for source in ref.findall(".//source"):
            parts.append("".join(source.itertext()).strip())
        for year in ref.findall(".//year"):
            if year.text:
                parts.append(year.text)
        if parts:
            refs.append(", ".join(parts))
    return refs
