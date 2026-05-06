"""Detect PMID / PMCID from a PDF filename or its extracted text.

PMIDs are 1-8 digit integers; effectively all real PMIDs are 7-9 digits as of 2026.
PMCIDs look like PMC1234567 (1-8 digit body).

Detection strategy:
  1. Filename — if the bare stem is digits-only (length 5-9), treat as PMID.
  2. Filename — explicit "PMID12345678" / "pmid_12345678" patterns.
  3. PDF text — first 4000 chars searched for "PMID: 12345678" or "PMC1234567".
"""
from __future__ import annotations
import re
from pathlib import Path

# A PMID is up to 8 digits (current max ~40M). We accept 5-9 digits to be safe.
_PMID_RE = re.compile(r"\bpmid\s*[:=]?\s*(\d{5,9})\b", re.IGNORECASE)
_PMCID_RE = re.compile(r"\bPMC\s*(\d{4,9})\b", re.IGNORECASE)
_PMID_FILENAME_RE = re.compile(r"(?:^|[^\d])pmid[_\-]?(\d{5,9})", re.IGNORECASE)


def detect_pmid_from_filename(filename: str | Path) -> str | None:
    """Return a PMID extracted from the filename, or None.

    Accepted forms (stem only, ignoring .pdf):
      "12345678.pdf"               -> "12345678"
      "PMID12345678.pdf"           -> "12345678"
      "pmid_12345678_supp.pdf"     -> "12345678"
    """
    stem = Path(filename).stem
    if not stem:
        return None
    bare = stem.strip()
    if bare.isdigit() and 5 <= len(bare) <= 9:
        return bare
    m = _PMID_FILENAME_RE.search(bare)
    if m:
        return m.group(1)
    return None


def detect_pmid_from_text(text: str, max_chars: int = 4000) -> str | None:
    """Search the first `max_chars` of `text` for an explicit PMID."""
    if not text:
        return None
    head = text[:max_chars]
    m = _PMID_RE.search(head)
    if m:
        return m.group(1)
    return None


def detect_pmcid_from_text(text: str, max_chars: int = 4000) -> str | None:
    """Search the first `max_chars` of `text` for a PMCID."""
    if not text:
        return None
    head = text[:max_chars]
    m = _PMCID_RE.search(head)
    if m:
        return m.group(1)
    return None


def safe_filename_stem(filename: str | Path, max_len: int = 64) -> str:
    """Filesystem/URL-safe stem from a filename, suitable for use as display_id."""
    stem = Path(filename).stem.strip()
    if not stem:
        return "paper"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_.-")
    return (safe or "paper")[:max_len]


def derive_display_id(filename: str | Path) -> tuple[str, str | None]:
    """Return (display_id, detected_pmid) from a filename only.

    Used at upload time before we have the PDF text. The pipeline can later
    enrich uploads.pmid by inspecting extracted text via detect_pmid_from_text.
    """
    pmid = detect_pmid_from_filename(filename)
    if pmid:
        return pmid, pmid
    return safe_filename_stem(filename), None


if __name__ == "__main__":
    samples = [
        "12345678.pdf",
        "PMID12345678.pdf",
        "pmid_12345678_supp.pdf",
        "study.pdf",
        "lung_cancer_2024.pdf",
        "weird name (1).pdf",
    ]
    for s in samples:
        print(f"{s:35s} -> {derive_display_id(s)}")
