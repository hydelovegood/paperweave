from __future__ import annotations

import logging
from pathlib import Path

from paperlab.config import load_settings
from paperlab.enrich.forward_citations import select_papers_for_citations, track_forward_citations

log = logging.getLogger(__name__)


def citations_forward_cmd(
    project_root: Path | str,
    paper_ids: list[int] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    max_results: int | None = None,
) -> list[int]:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()

    target_ids = paper_ids or select_papers_for_citations(db_path)
    if not target_ids:
        log.info("No papers for citation tracking.")
        return []

    all_citing: list[int] = []
    for pid in target_ids:
        try:
            citing_ids = track_forward_citations(
                root, pid, year_start=year_start, year_end=year_end, max_results=max_results,
            )
            all_citing.extend(citing_ids)
            log.info("Paper %d: found %d forward citations", pid, len(citing_ids))
        except Exception as exc:
            log.warning("Failed to track citations for paper %d: %s", pid, exc)

    return all_citing
