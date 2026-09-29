from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from paperlab.utils.hashing import sha256_file


@dataclass(frozen=True, slots=True)
class ScannedFile:
    path: Path
    filename: str
    sha256: str
    size_bytes: int
    mtime_utc: str


def discover_pdf_paths(target: Path | str, recursive: bool = False) -> list[Path]:
    resolved = Path(target).expanduser().resolve()

    if resolved.is_file():
        if resolved.suffix.lower() != ".pdf":
            raise ValueError(f"Target file is not a PDF: {resolved}")
        return [resolved]

    if not resolved.is_dir():
        raise FileNotFoundError(f"Target path does not exist: {resolved}")

    iterator = resolved.rglob("*.pdf") if recursive else resolved.glob("*.pdf")
    return sorted(path.resolve() for path in iterator if path.is_file())


def scan_target(
    target: Path | str,
    recursive: bool = False,
    known: dict[str, tuple[int, str, str]] | None = None,
) -> list[ScannedFile]:
    scanned: list[ScannedFile] = []

    for pdf_path in discover_pdf_paths(target, recursive=recursive):
        stat_result = pdf_path.stat()
        mtime_utc = datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat()
        # Skip re-hashing when the stored record has the same size and mtime.
        stored = known.get(str(pdf_path)) if known else None
        if stored is not None and stored[0] == stat_result.st_size and stored[1] == mtime_utc:
            sha256 = stored[2]
        else:
            sha256 = sha256_file(pdf_path)
        scanned.append(
            ScannedFile(
                path=pdf_path,
                filename=pdf_path.name,
                sha256=sha256,
                size_bytes=stat_result.st_size,
                mtime_utc=mtime_utc,
            )
        )

    return scanned
