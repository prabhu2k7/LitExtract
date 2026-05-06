"""Assemble prompts from a 4-level hierarchy + hash the resulting bundle."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Iterable

import config

AGENT_NAMES = ("study_details", "bm_details", "bm_results", "inferences")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _core_path(agent: str) -> Path:
    return config.PROMPTS_DIR / "core" / f"{agent}_core.txt"


def _disease_addon(agent: str, disease: str | None) -> Path | None:
    if not disease:
        return None
    p = config.PROMPTS_DIR / "diseases" / disease / f"{agent}_addon.txt"
    return p if p.exists() else None


def _study_type_addon(agent: str, stype: str) -> Path | None:
    p = config.PROMPTS_DIR / "study_types" / stype / f"{agent}_addon.txt"
    return p if p.exists() else None


def _bm_type_addon(agent: str, bmt: str) -> Path | None:
    p = config.PROMPTS_DIR / "bm_types" / bmt / f"{agent}_addon.txt"
    return p if p.exists() else None


def collect_prompt_files(agent: str,
                          disease: str | None,
                          study_types: Iterable[str],
                          bm_types: Iterable[str]) -> list[Path]:
    files: list[Path] = [_core_path(agent)]
    addon = _disease_addon(agent, disease)
    if addon:
        files.append(addon)
    for st in study_types or []:
        a = _study_type_addon(agent, st)
        if a:
            files.append(a)
    for bt in bm_types or []:
        a = _bm_type_addon(agent, bt)
        if a:
            files.append(a)
    return files


def compose_prompt(agent_name: str,
                    disease: str | None,
                    study_types: list[str],
                    bm_types: list[str],
                    document_data: dict) -> str:
    if agent_name not in AGENT_NAMES:
        raise ValueError(f"Unknown agent: {agent_name!r}")

    files = collect_prompt_files(agent_name, disease, study_types, bm_types)
    parts = [_read(p) for p in files if p.exists()]
    instructions = "\n\n".join(s for s in parts if s.strip())

    text_data = document_data.get("text_data", "") or ""
    table_data = document_data.get("table_data", "") or ""
    structured_tables = document_data.get("structured_tables_text", "") or ""
    pmid = document_data.get("pubmed_id", "")
    gap_header = document_data.get("_gap_fill_header", "")

    document_block = [
        f"=== PAPER PMID: {pmid} ===",
        "=== FULL TEXT ===",
        text_data,
    ]
    if structured_tables:
        document_block += ["", "=== STRUCTURED TABLES (Row/Col format) ===", structured_tables]
    if table_data:
        document_block += ["", "=== RAW MARKDOWN TABLES ===", table_data]

    header = ""
    if gap_header:
        header = f"\n=== GAP-FILL PASS ===\n{gap_header}\n"

    return f"{instructions}{header}\n\n" + "\n".join(document_block)


def get_prompt_hash(disease: str | None,
                     study_types: list[str],
                     bm_types: list[str],
                     agent_names: Iterable[str] = AGENT_NAMES) -> str:
    h = hashlib.sha256()
    for agent in agent_names:
        for f in collect_prompt_files(agent, disease, study_types, bm_types):
            if f.exists():
                h.update(f.read_bytes())
            h.update(str(f).encode("utf-8"))
    return h.hexdigest()[:12]
