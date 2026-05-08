"""Curated pharma-showcase PMID picker.

Instead of taking top-N by CIViC evidence count, this module targets ten
specific (biomarker × disease × variant) tuples that pharma evaluators
recognise immediately. Each tuple becomes one paper in the showcase.

Substitutions vs original "10 canonical pharma biomarkers" wishlist:
  - PD-L1/CD274 expression in NSCLC -> KEAP1 mutation in NSCLC (CIViC has
    rich variant curation; CIViC doesn't index expression-only biomarkers)
  - MSI-H/dMMR in CRC -> KRAS G12V in CRC (anti-EGFR resistance, well-curated)

Each tuple is (label, gene, disease_substring, variant_keywords).
`disease_substring` and `variant_keywords` match against CIViC's TSV
columns case-insensitively.
"""
from __future__ import annotations
from dataclasses import dataclass

import pandas as pd


@dataclass
class ShowcaseTarget:
    label: str                         # human-readable category name
    genes: tuple[str, ...]             # CIViC gene symbol(s) — any matches
    disease_substr: str                # case-insensitive substring of `disease`
    variant_keywords: tuple[str, ...]  # any matches `variant` (case-insens); empty = any
    drug_class: str                    # for the manifest / report only


# Ten canonical pharma scenarios. `genes` is a tuple to handle fusions whose
# CIViC gene symbol is e.g. "BCR::ABL1" (NOT just "ABL1"), and aliases.
SHOWCASE: tuple[ShowcaseTarget, ...] = (
    ShowcaseTarget("EGFR-NSCLC-TKI", ("EGFR",), "lung",
                   ("T790M", "L858R", "exon 19", "del19", "L747"), "TKI"),
    ShowcaseTarget("BRAF-Melanoma", ("BRAF",), "melanoma",
                   ("V600",), "BRAFi"),
    ShowcaseTarget("KRAS-NSCLC-G12C", ("KRAS",), "lung",
                   ("G12C",), "KRAS-G12Ci"),
    ShowcaseTarget("ALK-NSCLC", ("ALK", "EML4::ALK", "EML4-ALK"), "lung",
                   ("",), "ALKi"),
    ShowcaseTarget("HER2-Breast", ("ERBB2",), "breast",
                   ("",), "trastuzumab/ADC"),
    ShowcaseTarget("BRCA1-Ovarian", ("BRCA1", "BRCA2"), "ovarian",
                   ("",), "PARPi"),
    ShowcaseTarget("KRAS-CRC", ("KRAS",), "colorectal",
                   ("G12", "G13", "Q61"), "anti-EGFR resistance"),
    ShowcaseTarget("KEAP1-NSCLC", ("KEAP1",), "lung",
                   ("",), "chemo/IO resistance"),
    ShowcaseTarget("FLT3-AML", ("FLT3",), "leukemia",
                   ("ITD",), "FLT3i (midostaurin)"),
    ShowcaseTarget("BCR-ABL1-CML", ("BCR::ABL1", "ABL1"), "leukemia",
                   ("",), "imatinib + successors"),
    # New tissue-agnostic targets — added to replace ALK/FLT3 paywall gaps
    ShowcaseTarget("NTRK-fusion-tissue-agnostic",
                   ("NTRK1", "NTRK2", "NTRK3",
                    "ETV6::NTRK3", "TPM3::NTRK1", "LMNA::NTRK1"),
                   "",  # ANY disease — NTRK fusions are tissue-agnostic
                   ("fusion", "::", "rearr"),
                   "larotrectinib / entrectinib (tissue-agnostic)"),
    ShowcaseTarget("IDH1-AML",
                   ("IDH1",),
                   "leukemia",
                   ("R132", "mutation"),
                   "ivosidenib"),
)


def _matches_target(row: pd.Series, t: ShowcaseTarget) -> bool:
    """Does this CIViC row match a showcase target?"""
    gene = str(row.get("gene") or "").strip().upper()
    if gene not in {g.upper() for g in t.genes}:
        return False
    disease = str(row.get("disease") or "").lower()
    if t.disease_substr.lower() not in disease:
        return False
    if not any(t.variant_keywords) or t.variant_keywords == ("",):
        return True
    variant = str(row.get("variant") or "").lower()
    return any(kw.lower() in variant for kw in t.variant_keywords if kw)


def select_curated(df: pd.DataFrame, top_k: int = 10
                   ) -> list[tuple[str, ShowcaseTarget, int]]:
    """Return up to `top_k` candidate PMIDs per showcase target.

    The downloader (in build_goldset.py) tries each in turn and keeps the
    first OA-available one per target. This handles the reality that the
    most-curated CIViC papers tend to be paywalled landmarks (NEJM, JCO,
    Nat Med); top-K gives us OA-friendly fallbacks.

    Returns: list of (pmid, target, evidence_count). Multiple rows may share
    the same target.
    """
    selected: list[tuple[str, ShowcaseTarget, int]] = []
    for t in SHOWCASE:
        mask = df.apply(lambda r: _matches_target(r, t), axis=1)
        sub = df[mask]
        if sub.empty:
            print(f"      [no match] {t.label}: genes={t.genes} disease~'{t.disease_substr}' variants={t.variant_keywords}")
            continue
        counts = sub.groupby("pmid").size().sort_values(ascending=False)
        picked = list(counts.head(top_k).items())
        for pmid, n in picked:
            selected.append((str(pmid), t, int(n)))
        labels = ", ".join(f"{p}({n})" for p, n in picked[:3])
        more = f" +{len(picked) - 3} more" if len(picked) > 3 else ""
        print(f"      [{len(picked)} candidates] {t.label:<22s} top: {labels}{more}")
    return selected
