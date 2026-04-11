from __future__ import annotations


_BIOMED_JOURNAL_KEYWORDS = (
    "med", "clin", "lancet", "nejm", "bmj", "jama", "nature med",
    "bioeng", "biomed", "pharmacol", "oncology", "cardiol", "neurol",
    "radiol", "surg", "nurs", "dental", "vet", "epidemiol", "transl",
)

_BIOMED_PUB_TYPES = (
    "clinical trial",
    "randomized controlled trial",
    "meta-analysis",
    "systematic review",
    "case report",
    "cohort",
    "case-control",
)


def classify_paper(paper: dict) -> str:
    """Classify paper domain. Returns 'biomedical', 'cs', or 'general'."""
    if paper.get("pmid") or paper.get("mesh_terms"):
        return "biomedical"

    pub_type = (paper.get("publication_type") or "").lower()
    if any(t in pub_type for t in _BIOMED_PUB_TYPES):
        return "biomedical"

    journal = (paper.get("journal") or "").lower()
    if any(kw in journal for kw in _BIOMED_JOURNAL_KEYWORDS):
        return "biomedical"

    if paper.get("arxiv_id"):
        return "cs"

    return "general"
