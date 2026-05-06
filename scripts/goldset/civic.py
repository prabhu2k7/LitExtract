"""CIViC (Clinical Interpretation of Variants in Cancer) data fetcher.

CIViC publishes a nightly TSV export of all clinical evidence summaries:
each row = one curated fact (gene + variant + disease + drug + evidence
direction + clinical significance + supporting PMID).

Public, free, CC0-licensed. https://docs.civicdb.org/en/latest/about.html

This module:
  1. Downloads the nightly TSV (cached locally in `D:\\dev\\pubmed_files\\`)
  2. Provides filtering helpers for pharma-priority diseases and high-quality
     evidence levels.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterable

import requests
import pandas as pd

CIVIC_NIGHTLY_TSV = (
    "https://civicdb.org/downloads/nightly/nightly-ClinicalEvidenceSummaries.tsv"
)

# Diseases pharma R&D actively prioritises (top oncology revenue lines).
# Matched case-insensitively as substrings against CIViC's `disease` column.
PHARMA_DISEASE_PRIORITIES: tuple[str, ...] = (
    "lung",            # NSCLC, SCLC, lung adenocarcinoma
    "breast",          # all subtypes
    "colorectal",
    "colon",
    "rectal",
    "melanoma",
    "hepatocellular",
    "liver",
    "prostate",
    "ovarian",
    "pancreatic",
    "gastric",
    "stomach",
    "renal",
    "kidney",
    "bladder",
    "urothelial",
    "glioma",
    "glioblastoma",
    "leukemia",
    "myeloma",
    "lymphoma",
    "thyroid",
    "esophag",
    "head and neck",
    "endometrial",
    "cervical",
)

# Evidence types we extract / care about. Predictive (treatment response) is
# the most pharma-relevant; Prognostic and Diagnostic also map to our schema.
USEFUL_EVIDENCE_TYPES = ("Predictive", "Prognostic", "Diagnostic")

# Skip preclinical (level D) and inferential (level E if present) — keep
# clinically-meaningful evidence only.
USEFUL_EVIDENCE_LEVELS = ("A", "B", "C")


def fetch_civic_tsv(cache_dir: Path) -> Path:
    """Download (or return cached) CIViC nightly TSV.

    Cached as `civic-evidence-YYYYMMDD.tsv` in `cache_dir`. Re-fetched if the
    cache file is older than today.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    target = cache_dir / f"civic-evidence-{today}.tsv"
    if target.exists() and target.stat().st_size > 0:
        return target

    print(f"  fetching {CIVIC_NIGHTLY_TSV} ...")
    r = requests.get(
        CIVIC_NIGHTLY_TSV,
        timeout=120,
        headers={"User-Agent": "Mozilla/5.0 LitExtract-goldset/0.4"},
    )
    r.raise_for_status()
    target.write_bytes(r.content)
    print(f"  cached at {target} ({len(r.content)/1024:.0f} KB)")
    return target


def load_civic(tsv_path: Path) -> pd.DataFrame:
    """Load + lightly clean the CIViC TSV. Returns DataFrame."""
    df = pd.read_csv(tsv_path, sep="\t", low_memory=False)
    # Normalise PMID column (it's `citation_id` in the nightly export, with
    # `source_type == 'PubMed'` rows being the ones we want).
    if "pubmed_id" in df.columns:
        df = df.rename(columns={"pubmed_id": "pmid"})
    if "citation_id" in df.columns and "source_type" in df.columns:
        df["pmid"] = df.apply(
            lambda r: str(r["citation_id"])
            if str(r.get("source_type", "")).lower() == "pubmed"
            else "",
            axis=1,
        )
    if "pmid" not in df.columns:
        raise RuntimeError(f"CIViC TSV missing PMID column. Columns: {list(df.columns)}")
    df["pmid"] = df["pmid"].fillna("").astype(str).str.strip()
    df = df[df["pmid"].str.match(r"^\d+$", na=False)]

    # CIViC's nightly TSV stores gene+variant in a single `molecular_profile`
    # column (e.g. "JAK2 V617F"). Split into `gene` + `variant` so downstream
    # consumers can use them naturally.
    if "molecular_profile" in df.columns and "gene" not in df.columns:
        mp = df["molecular_profile"].fillna("").astype(str)
        df["gene"] = mp.str.split(r"\s+", n=1, regex=True).str[0].fillna("")
        df["variant"] = mp.str.split(r"\s+", n=1, regex=True).str[1].fillna("")

    # Aliases so downstream code can use the friendlier names without caring
    # which CIViC export schema is current.
    if "therapies" in df.columns and "drugs" not in df.columns:
        df["drugs"] = df["therapies"].fillna("").astype(str)
    if "significance" in df.columns and "clinical_significance" not in df.columns:
        df["clinical_significance"] = df["significance"].fillna("").astype(str)

    return df


def filter_useful(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows likely to map cleanly into our 4-sheet schema."""
    # Status filter — only accepted (peer-reviewed by CIViC curators)
    if "evidence_status" in df.columns:
        df = df[df["evidence_status"].fillna("").str.lower() == "accepted"]
    # Type filter
    if "evidence_type" in df.columns:
        df = df[df["evidence_type"].isin(USEFUL_EVIDENCE_TYPES)]
    # Level filter
    if "evidence_level" in df.columns:
        df = df[df["evidence_level"].isin(USEFUL_EVIDENCE_LEVELS)]
    return df


def filter_pharma_relevant(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows whose `disease` matches a pharma-priority indication."""
    if "disease" not in df.columns:
        return df
    pat = "|".join(PHARMA_DISEASE_PRIORITIES)
    mask = df["disease"].fillna("").str.contains(pat, case=False, regex=True)
    return df[mask]


def select_25_pmids(df: pd.DataFrame, target_count: int = 25) -> list[str]:
    """Select diverse, high-quality PMIDs.

    Strategy:
      1. Group by PMID, count CIViC evidence items.
      2. Sort by (evidence_count DESC, has_level_A DESC).
      3. Greedily pick PMIDs while spreading across diseases (max 4 per disease).
    """
    # Per-PMID summary
    g = df.groupby("pmid").agg(
        evidence_count=("pmid", "size"),
        diseases=("disease", lambda s: sorted(set(s.dropna()))[:3]),
        genes=("gene", lambda s: sorted(set(s.dropna()))[:3]) if "gene" in df.columns else ("pmid", "size"),
        has_a=("evidence_level", lambda s: "A" in set(s)),
        primary_disease=("disease", lambda s: s.value_counts().idxmax() if len(s) else ""),
        evidence_types=("evidence_type", lambda s: sorted(set(s.dropna()))),
    ).reset_index()

    g = g.sort_values(
        by=["has_a", "evidence_count"],
        ascending=[False, False],
    )

    selected: list[str] = []
    per_disease: dict[str, int] = {}
    for _, r in g.iterrows():
        if len(selected) >= target_count:
            break
        d = (r["primary_disease"] or "").strip().lower()
        # Cap diversity: max 4 papers per primary disease
        if per_disease.get(d, 0) >= 4:
            continue
        selected.append(str(r["pmid"]))
        per_disease[d] = per_disease.get(d, 0) + 1

    return selected
