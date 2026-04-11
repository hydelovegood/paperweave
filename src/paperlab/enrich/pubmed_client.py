from __future__ import annotations

import xml.etree.ElementTree as ET

from paperlab.enrich.http import get_json

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def resolve_by_doi(doi: str, api_key: str = "") -> dict | None:
    params = {
        "db": "pubmed",
        "term": f"{doi}[DOI]",
        "retmode": "xml",
        "retmax": 1,
    }
    if api_key:
        params["api_key"] = api_key
    resp = get_json(f"{_BASE}/esearch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    id_list = _parse_esearch_xml(resp.text)
    if not id_list:
        return None
    return _fetch_by_pmid(id_list[0], api_key)


def resolve_by_title(title: str, api_key: str = "") -> dict | None:
    params = {
        "db": "pubmed",
        "term": f"{title}[Title]",
        "retmode": "xml",
        "retmax": 1,
    }
    if api_key:
        params["api_key"] = api_key
    resp = get_json(f"{_BASE}/esearch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    id_list = _parse_esearch_xml(resp.text)
    if not id_list:
        return None
    return _fetch_by_pmid(id_list[0], api_key)


def _parse_esearch_xml(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    return [
        element.text
        for element in root.findall(".//IdList/Id")
        if element.text
    ]


def _fetch_by_pmid(pmid: str, api_key: str = "") -> dict | None:
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key
    resp = get_json(f"{_BASE}/efetch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    return _parse_pubmed_xml(resp.text)


def _parse_pubmed_xml(xml_text: str) -> dict | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    article = root.find(".//PubmedArticle/MedlineCitation/Article")
    if article is None:
        return None

    medline = root.find(".//PubmedArticle/MedlineCitation")
    pmid_el = medline.find("PMID") if medline is not None else None
    pmid = pmid_el.text if pmid_el is not None else None

    title_el = article.find("ArticleTitle")
    title = title_el.text if title_el is not None else None

    journal_el = article.find("Journal/Title")
    journal = journal_el.text if journal_el is not None else None

    year = _extract_year(article)

    doi = None
    for aid in root.findall(".//ArticleId"):
        if aid.get("IdType") == "doi":
            doi = aid.text
            break

    pmcid = None
    for aid in root.findall(".//ArticleId"):
        if aid.get("IdType") == "pmc":
            pmcid = aid.text
            break

    pub_types = [
        pt.text for pt in article.findall(".//PublicationTypeList/PublicationType")
        if pt.text
    ]
    publication_type = pub_types[0] if pub_types else None

    mesh_terms = [
        mh.find("DescriptorName").text
        for mh in root.findall(".//MeshHeadingList/MeshHeading")
        if mh.find("DescriptorName") is not None and mh.find("DescriptorName").text
    ]

    abstract_parts = []
    for text_el in article.findall(".//Abstract/AbstractText"):
        label = text_el.get("Label")
        text = "".join(text_el.itertext()).strip()
        if text:
            abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(abstract_parts) if abstract_parts else None

    return {
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": title,
        "journal": journal,
        "year": year,
        "publication_type": publication_type,
        "mesh_terms": mesh_terms,
        "abstract": abstract,
    }


def _extract_year(article: ET.Element) -> int | None:
    for path in (
        "Journal/JournalIssue/PubDate/Year",
        "Journal/JournalIssue/PubDate/MedlineDate",
    ):
        el = article.find(path)
        if el is not None and el.text:
            year_str = el.text[:4]
            if year_str.isdigit():
                return int(year_str)
    return None


def get_forward_citations(
    pmid: str,
    year_start: int,
    year_end: int,
    max_results: int,
    api_key: str = "",
) -> list[dict]:
    """Get papers that cite the given PMID, using NCBI elink API."""
    params = {
        "dbfrom": "pubmed",
        "db": "pubmed",
        "id": pmid,
        "cmd": "neighbor_score",
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    resp = get_json(f"{_BASE}/elink.fcgi", params=params, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()

    linksets = data.get("linksets", [])
    citing_pmids = []
    for linkset in linksets:
        for linksetdb in linkset.get("linksetdbs", []):
            if "pubmed_pubmed_citedin" in linksetdb.get("db", ""):
                citing_pmids.extend(linksetdb.get("links", []))

    if not citing_pmids:
        return []

    citing_pmids = citing_pmids[:max_results]

    # Batch fetch metadata for citing PMIDs
    results = []
    batch_size = 50
    for i in range(0, len(citing_pmids), batch_size):
        batch = citing_pmids[i : i + batch_size]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key
        batch_resp = get_json(f"{_BASE}/efetch.fcgi", params=params, timeout=30)
        batch_resp.raise_for_status()
        articles = _parse_batch_xml(batch_resp.text)
        for article in articles:
            year = article.get("year")
            if year and year_start <= year <= year_end:
                results.append(article)

    return results


def _parse_batch_xml(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    results = []
    for article_el in root.findall(".//PubmedArticle"):
        medline = article_el.find("MedlineCitation")
        article = medline.find("Article") if medline is not None else None
        if article is None:
            continue

        pmid_el = medline.find("PMID") if medline is not None else None
        pmid = pmid_el.text if pmid_el is not None else None

        title_el = article.find("ArticleTitle")
        title = title_el.text if title_el is not None else None

        journal_el = article.find("Journal/Title")
        journal = journal_el.text if journal_el is not None else None

        year = _extract_year(article)

        doi = None
        for aid in article_el.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
                break

        results.append({
            "pmid": pmid,
            "doi": doi,
            "title": title,
            "journal": journal,
            "year": year,
        })

    return results
