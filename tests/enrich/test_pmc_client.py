from __future__ import annotations

from paperlab.enrich.pmc_client import parse_jats_xml
from paperlab.parsing.canonical import CanonicalPaper


def _sample_jats():
    return """<?xml version="1.0"?>
<article>
  <front>
    <journal-meta>
      <journal-title>The Lancet</journal-title>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="doi">10.1016/test.2024.001</article-id>
      <article-id pub-id-type="arxiv">2401.12345</article-id>
      <pub-date><year>2024</year></pub-date>
      <title-group>
        <article-title>A novel treatment for hypertension</article-title>
      </title-group>
      <contrib-group>
        <contrib>
          <name><given-names>Jane</given-names><surname>Smith</surname></name>
        </contrib>
        <contrib>
          <name><given-names>John</given-names><surname>Doe</surname></name>
        </contrib>
      </contrib-group>
      <abstract>
        <sec>
          <title>Background</title>
          <p>Hypertension is a major risk factor.</p>
        </sec>
        <sec>
          <title>Methods</title>
          <p>We conducted a randomized trial.</p>
        </sec>
        <sec>
          <title>Results</title>
          <p>Drug X lowered systolic BP by 12 mmHg.</p>
        </sec>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Introduction</title>
      <p>Hypertension affects over 1 billion people worldwide.</p>
    </sec>
    <sec>
      <title>Methods</title>
      <p>We enrolled 500 patients across 12 centers.</p>
      <sec>
        <title>Statistical Analysis</title>
        <p>Power was set at 80% with alpha 0.05.</p>
      </sec>
    </sec>
    <sec>
      <title>Results</title>
      <p>The primary endpoint was achieved.</p>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref>
        <element-citation publication-type="journal">
          <article-title>Previous work on BP</article-title>
          <source>Circulation</source>
          <year>2022</year>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>"""


def test_parse_jats_extracts_title():
    paper = parse_jats_xml(_sample_jats())
    assert paper is not None
    assert paper.title == "A novel treatment for hypertension"


def test_parse_jats_extracts_journal_and_year():
    paper = parse_jats_xml(_sample_jats())
    assert paper.venue == "The Lancet"
    assert paper.year == 2024


def test_parse_jats_extracts_doi_and_arxiv():
    paper = parse_jats_xml(_sample_jats())
    assert paper.doi == "10.1016/test.2024.001"
    assert paper.arxiv_id == "2401.12345"


def test_parse_jats_extracts_structured_abstract():
    paper = parse_jats_xml(_sample_jats())
    assert "Background: Hypertension is a major risk factor." in paper.abstract
    assert "Results: Drug X lowered systolic BP by 12 mmHg." in paper.abstract


def test_parse_jats_extracts_authors():
    paper = parse_jats_xml(_sample_jats())
    assert len(paper.authors) == 2
    assert paper.authors[0]["name"] == "Jane Smith"
    assert paper.authors[1]["name"] == "John Doe"


def test_parse_jats_extracts_sections():
    paper = parse_jats_xml(_sample_jats())
    names = [s.name for s in paper.sections]
    assert "Introduction" in names
    assert "Methods" in names
    assert "Results" in names


def test_parse_jats_includes_subsection_text():
    paper = parse_jats_xml(_sample_jats())
    methods = [s for s in paper.sections if s.name == "Methods"][0]
    assert "Power was set at 80%" in methods.text


def test_parse_jats_extracts_references():
    paper = parse_jats_xml(_sample_jats())
    assert len(paper.references_raw) == 1
    assert "Previous work on BP" in paper.references_raw[0]


def test_parse_jats_source_is_pmc():
    paper = parse_jats_xml(_sample_jats())
    assert paper.source == "pmc"


def test_fetch_fulltext_xml_returns_xml_string(monkeypatch):
    from paperlab.enrich.pmc_client import fetch_fulltext_xml

    response = type("R", (), {
        "status_code": 200,
        "text": "<article><front></front></article>",
        "raise_for_status": lambda self: None,
    })()

    monkeypatch.setattr(
        "paperlab.enrich.pmc_client.get_json",
        lambda *args, **kwargs: response,
    )

    xml_text = fetch_fulltext_xml("PMC1234567")
    assert xml_text == "<article><front></front></article>"


def test_parse_jats_returns_none_on_invalid_xml():
    assert parse_jats_xml("not xml") is None
    result = parse_jats_xml("<empty/>")
    assert result is not None
    assert result.title == ""
    assert result.sections == []


def test_canonical_paper_accepts_medical_fields():
    paper = CanonicalPaper(
        source="pmc",
        paper_id="paper-test",
        title="Test",
        authors=[],
        abstract="",
        year=2024,
        venue="NEJM",
        doi=None,
        arxiv_id=None,
        sections=[],
        references_raw=[],
        full_text="",
        parse_quality=1.0,
        pmid="12345678",
        pmcid="PMC9876543",
        journal="NEJM",
        mesh_terms=["Hypertension", "Drug Therapy"],
        publication_type="Clinical Trial",
    )
    assert paper.pmid == "12345678"
    assert paper.pmcid == "PMC9876543"
    assert "Hypertension" in paper.mesh_terms

    d = paper.to_dict()
    assert d["pmid"] == "12345678"
    assert d["mesh_terms"] == ["Hypertension", "Drug Therapy"]
