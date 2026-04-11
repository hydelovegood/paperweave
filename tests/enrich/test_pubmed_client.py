from __future__ import annotations

from paperlab.enrich.pubmed_client import _parse_pubmed_xml, _parse_batch_xml


def test_parse_pubmed_xml_extracts_fields():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>12345678</PMID>
          <Article>
            <Journal>
              <Title>The Lancet</Title>
              <JournalIssue>
                <PubDate><Year>2024</Year></PubDate>
              </JournalIssue>
            </Journal>
            <ArticleTitle>A novel treatment for hypertension</ArticleTitle>
            <Abstract>
              <AbstractText Label="BACKGROUND">Hypertension is common.</AbstractText>
              <AbstractText Label="METHODS">We did an RCT.</AbstractText>
              <AbstractText Label="RESULTS">Drug X lowered BP by 10 mmHg.</AbstractText>
            </Abstract>
            <PublicationTypeList>
              <PublicationType>Journal Article</PublicationType>
              <PublicationType>Clinical Trial</PublicationType>
            </PublicationTypeList>
          </Article>
          <MeshHeadingList>
            <MeshHeading><DescriptorName>Hypertension</DescriptorName></MeshHeading>
            <MeshHeading><DescriptorName>Drug Therapy</DescriptorName></MeshHeading>
          </MeshHeadingList>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1016/test.2024.001</ArticleId>
            <ArticleId IdType="pmc">PMC9876543</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>"""

    result = _parse_pubmed_xml(xml)

    assert result is not None
    assert result["pmid"] == "12345678"
    assert result["title"] == "A novel treatment for hypertension"
    assert result["journal"] == "The Lancet"
    assert result["year"] == 2024
    assert result["doi"] == "10.1016/test.2024.001"
    assert result["pmcid"] == "PMC9876543"
    assert result["publication_type"] == "Journal Article"
    assert "Hypertension" in result["mesh_terms"]
    assert "Drug Therapy" in result["mesh_terms"]


def test_parse_esearch_xml_extracts_id_list():
    from paperlab.enrich.pubmed_client import _parse_esearch_xml

    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <eSearchResult>
      <Count>1</Count>
      <RetMax>1</RetMax>
      <RetStart>0</RetStart>
      <IdList>
        <Id>41862772</Id>
      </IdList>
    </eSearchResult>
    """

    assert _parse_esearch_xml(xml) == ["41862772"]


def test_parse_pubmed_xml_returns_none_on_empty():
    result = _parse_pubmed_xml("<empty/>")
    assert result is None


def test_parse_pubmed_xml_handles_missing_fields():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>99999</PMID>
          <Article>
            <Journal><Title>Some Journal</Title></Journal>
            <ArticleTitle>Minimal paper</ArticleTitle>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>"""

    result = _parse_pubmed_xml(xml)

    assert result is not None
    assert result["pmid"] == "99999"
    assert result["doi"] is None
    assert result["pmcid"] is None
    assert result["mesh_terms"] == []
    assert result["abstract"] is None
    assert result["publication_type"] is None


def test_resolve_by_doi_with_mock(monkeypatch):
    from paperlab.enrich import pubmed_client

    search_response = type("R", (), {
        "status_code": 200,
        "text": """<?xml version="1.0"?><eSearchResult><IdList><Id>11111</Id></IdList></eSearchResult>""",
        "json": lambda self: {},
        "raise_for_status": lambda self: None,
    })()

    fetch_xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>11111</PMID>
          <Article>
            <Journal><Title>NEJM</Title>
              <JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue>
            </Journal>
            <ArticleTitle>Test paper</ArticleTitle>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1056/test</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>"""

    fetch_response = type("R", (), {
        "status_code": 200,
        "text": fetch_xml,
        "json": lambda self: {},
        "raise_for_status": lambda self: None,
    })()

    call_count = [0]

    def fake_get_json(url, **kwargs):
        call_count[0] += 1
        if "esearch" in url:
            return search_response
        return fetch_response

    monkeypatch.setattr("paperlab.enrich.pubmed_client.get_json", fake_get_json)

    result = pubmed_client.resolve_by_doi("10.1056/test")
    assert result is not None
    assert result["pmid"] == "11111"
    assert result["doi"] == "10.1056/test"
    assert call_count[0] == 2


def test_resolve_by_doi_not_found(monkeypatch):
    from paperlab.enrich import pubmed_client

    response = type("R", (), {
        "status_code": 200,
        "text": """<?xml version="1.0"?><eSearchResult><IdList></IdList></eSearchResult>""",
        "json": lambda self: {},
        "raise_for_status": lambda self: None,
    })()

    monkeypatch.setattr(
        "paperlab.enrich.pubmed_client.get_json",
        lambda *a, **kw: response,
    )

    result = pubmed_client.resolve_by_doi("10.0000/nonexistent")
    assert result is None


def test_get_forward_citations_with_mock(monkeypatch):
    from paperlab.enrich import pubmed_client

    elink_response = type("R", (), {
        "status_code": 200,
        "text": "",
        "json": lambda self: {
            "linksets": [{
                "linksetdbs": [{
                    "db": "pubmed_pubmed_citedin",
                    "links": ["22222", "33333"],
                }]
            }]
        },
        "raise_for_status": lambda self: None,
    })()

    batch_xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>22222</PMID>
          <Article>
            <Journal><Title>NEJM</Title>
              <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
            </Journal>
            <ArticleTitle>Citing paper A</ArticleTitle>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1056/citerA</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>33333</PMID>
          <Article>
            <Journal><Title>JAMA</Title>
              <JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue>
            </Journal>
            <ArticleTitle>Citing paper B</ArticleTitle>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1001/citerB</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>"""

    batch_response = type("R", (), {
        "status_code": 200,
        "text": batch_xml,
        "json": lambda self: {},
        "raise_for_status": lambda self: None,
    })()

    def fake_get_json(url, **kwargs):
        if "elink" in url:
            return elink_response
        return batch_response

    monkeypatch.setattr("paperlab.enrich.pubmed_client.get_json", fake_get_json)

    results = pubmed_client.get_forward_citations("11111", 2024, 2025, 10)
    assert len(results) == 2
    assert results[0]["pmid"] == "22222"
    assert results[0]["title"] == "Citing paper A"
    assert results[0]["doi"] == "10.1056/citerA"
    assert results[1]["pmid"] == "33333"


def test_get_forward_citations_year_filter(monkeypatch):
    from paperlab.enrich import pubmed_client

    elink_response = type("R", (), {
        "status_code": 200,
        "text": "",
        "json": lambda self: {
            "linksets": [{
                "linksetdbs": [{
                    "db": "pubmed_pubmed_citedin",
                    "links": ["22222", "33333"],
                }]
            }]
        },
        "raise_for_status": lambda self: None,
    })()

    batch_xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>22222</PMID>
          <Article>
            <Journal><Title>NEJM</Title>
              <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
            </Journal>
            <ArticleTitle>Old citing paper</ArticleTitle>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>33333</PMID>
          <Article>
            <Journal><Title>JAMA</Title>
              <JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue>
            </Journal>
            <ArticleTitle>New citing paper</ArticleTitle>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>"""

    batch_response = type("R", (), {
        "status_code": 200,
        "text": batch_xml,
        "json": lambda self: {},
        "raise_for_status": lambda self: None,
    })()

    def fake_get_json(url, **kwargs):
        if "elink" in url:
            return elink_response
        return batch_response

    monkeypatch.setattr("paperlab.enrich.pubmed_client.get_json", fake_get_json)

    results = pubmed_client.get_forward_citations("11111", 2024, 2026, 10)
    assert len(results) == 1
    assert results[0]["pmid"] == "33333"


def test_get_forward_citations_no_links(monkeypatch):
    from paperlab.enrich import pubmed_client

    response = type("R", (), {
        "status_code": 200,
        "text": "",
        "json": lambda self: {"linksets": [{"linksetdbs": []}]},
        "raise_for_status": lambda self: None,
    })()

    monkeypatch.setattr(
        "paperlab.enrich.pubmed_client.get_json",
        lambda *a, **kw: response,
    )

    results = pubmed_client.get_forward_citations("11111", 2024, 2026, 10)
    assert results == []


def test_parse_batch_xml():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>100</PMID>
          <Article>
            <Journal><Title>Lancet</Title>
              <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
            </Journal>
            <ArticleTitle>Paper 100</ArticleTitle>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1016/p100</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>"""

    results = _parse_batch_xml(xml)
    assert len(results) == 1
    assert results[0]["pmid"] == "100"
    assert results[0]["doi"] == "10.1016/p100"
