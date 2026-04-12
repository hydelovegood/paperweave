from __future__ import annotations

import logging
from pathlib import Path

from paperlab.config import load_settings
from paperlab.ingest.registry import IngestResult, register_scanned_files
from paperlab.ingest.scanner import scan_target

log = logging.getLogger(__name__)


def ingest_path(project_root: Path | str, target: Path | str, recursive: bool = False) -> IngestResult:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}. Run `paperweave init {root}` first.")
    scanned_files = scan_target(target, recursive=recursive)
    return register_scanned_files(db_path, scanned_files)
