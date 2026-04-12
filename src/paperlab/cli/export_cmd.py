from __future__ import annotations

import logging
from pathlib import Path

from paperlab.config import load_settings
from paperlab.export.qa_export import export_qa
from paperlab.export.summary_export import export_summary

log = logging.getLogger(__name__)


def export_summary_cmd(project_root: Path | str) -> int:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()
    output_path = root / settings.export.summary_file

    count = export_summary(db_path, output_path)
    log.info("Exported %d summary(ies) to %s", count, output_path)
    return count


def export_qa_cmd(project_root: Path | str) -> int:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()
    output_path = root / settings.export.qa_file

    count = export_qa(db_path, output_path)
    log.info("Exported %d paper(s) QA to %s", count, output_path)
    return count
