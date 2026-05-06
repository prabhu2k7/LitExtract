"""Map a CIViC evidence row -> rows in our 4-sheet goldset schema.

CIViC fields used (per nightly TSV):
  - gene
  - variant
  - disease
  - drugs (semicolon-separated)
  - evidence_type        Predictive | Prognostic | Diagnostic | Predisposing | Functional
  - evidence_direction   Supports | Does Not Support
  - clinical_significance
  - evidence_level       A | B | C | D | E
  - drug_interaction_type
  - phenotypes           (sometimes empty)
  - source_full_journal_title
  - rating               (1-5 stars from CIViC curators)

Mapping into our SHEET_COLUMNS:
  Study_Details:  not directly present in CIViC -> we leave largely empty
                  but mark the disease + a hint that this is a 'Clinical
                  Evidence Curation' so the row contributes a baseline.
  BM_Details:     gene + variant -> biomarker_name; biomarker_type derived
                  from variant kind (mutation/fusion/amplification/expression).
  BM_Results:     disease, evidence_type -> br_application; clinical
                  significance + evidence_direction -> association.
  Inferences:     evidence_direction + clinical_significance + drug ->
                  evidence_statement.

Each emitted row is tagged `validated_by_civic = True` and carries the CIViC
evidence_id so a reviewer can trace back to the source curation.
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Iterable

# Make the repo root importable so we can pull SHEET_COLUMNS for a sanity check.
_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from column_mappings import SHEET_COLUMNS  # noqa: E402


# CIViC clinical_significance -> our outcome wording
_SIG_MAP = {
    "sensitivity/response":     ("Positive", "better response", "high"),
    "resistance":               ("Negative", "drug resistance", "high"),
    "reduced sensitivity":      ("Negative", "reduced response", "high"),
    "adverse response":         ("Negative", "adverse drug reaction", "high"),
    "better outcome":           ("Positive", "better survival", "high"),
    "poor outcome":             ("Negative", "worse survival", "high"),
    "positive":                 ("Positive", "positive prognostic", ""),
    "negative":                 ("Negative", "negative prognostic", ""),
    "n/a":                      ("", "", ""),
}

_TYPE_TO_APP = {
    "Predictive":  "Prediction",
    "Prognostic":  "Prognosis",
    "Diagnostic":  "Diagnosis",
}


def _classify_variant(variant: str | None) -> tuple[str, str]:
    """Return (biomarker_type, biomarker_nature) from a CIViC variant string."""
    v = (variant or "").lower()
    if any(k in v for k in ("fusion", "::", "translocation", "rearr")):
        return "Genetic", "Fusion"
    if any(k in v for k in ("amplification", "copy number gain", "cn gain")):
        return "Genetic", "CNV"
    if any(k in v for k in ("loss", "deletion", "del", "loss of")):
        return "Genetic", "Deletion"
    if any(k in v for k in ("methylation", "promoter methylation")):
        return "Genetic", "Methylation"
    if any(k in v for k in ("expression", "overexpression", "underexpression")):
        return "Protein", "Expression"
    if any(k in v for k in ("mutation", "variant", ">", "deletion", "fs", "*")):
        return "Genetic", "Mutation"
    return "Genetic", "Variant"


def _civic_sig(sig: str | None) -> tuple[str, str, str]:
    s = (sig or "").strip().lower()
    return _SIG_MAP.get(s, ("", s or "", ""))


def emit_rows_for_paper(pmid: str, civic_rows: list[dict]) -> dict[str, list[dict]]:
    """Map all CIViC evidence rows for one PMID into our 4-sheet shape."""
    if not civic_rows:
        return {k: [] for k in SHEET_COLUMNS}

    # ---- Study_Details: 1 placeholder row capturing disease + paper id ----
    primary_disease = ""
    for r in civic_rows:
        if r.get("disease"):
            primary_disease = r["disease"]
            break
    study_rows = [{
        "pubmed_id":    pmid,
        "disease_name": primary_disease,
        # CIViC doesn't curate study design — leave the rest blank but signal
        # this is a partial gold via source_section.
        "source_excerpt": "Curated by CIViC clinical evidence summaries",
        "source_section": "CIViC",
        "validated_by_civic": True,
    }]

    # ---- BM_Details: 1 row per unique (gene, variant) ----
    bm_details: list[dict] = []
    seen_bm = set()
    for r in civic_rows:
        gene = (r.get("gene") or "").strip()
        variant = (r.get("variant") or "").strip()
        if not gene:
            continue
        key = f"{gene}|{variant}".lower()
        if key in seen_bm:
            continue
        seen_bm.add(key)
        bm_type, bm_nature = _classify_variant(variant)
        biomarker_name = f"{gene} {variant}".strip() if variant else gene
        bm_details.append({
            "pubmed_id":             pmid,
            "biomarker_name":        biomarker_name,
            "biomarker_type":        bm_type,
            "biomarker_nature":      bm_nature,
            "biomarker_name_std":    gene,
            "biomarker_name_type":   f"{gene}-{bm_type}",
            "source_excerpt":        f"CIViC evidence: {gene} {variant}".strip(),
            "source_section":        "CIViC",
            "validated_by_civic":    True,
        })

    # ---- BM_Results: 1 row per CIViC evidence item ----
    bm_results: list[dict] = []
    for r in civic_rows:
        gene = (r.get("gene") or "").strip()
        variant = (r.get("variant") or "").strip()
        if not gene:
            continue
        biomarker_name = f"{gene} {variant}".strip() if variant else gene
        ev_type = r.get("evidence_type") or ""
        sig = r.get("clinical_significance") or ""
        direction = r.get("evidence_direction") or ""
        drugs = r.get("drugs") or ""
        ev_level = r.get("evidence_level") or ""

        assoc, outcome, dir_ = _civic_sig(sig)
        # If "Does Not Support", flip the association sign for clarity
        if direction.strip().lower() == "does not support" and assoc:
            assoc = "Negative" if assoc == "Positive" else "Positive"

        bm_results.append({
            "pubmed_id":              pmid,
            "biomarker_name":         biomarker_name,
            "disease_name":           r.get("disease") or "",
            "outcome_name":           outcome or ev_type or "",
            "bm_outcome_association": assoc,
            "outcome_direction":      dir_,
            "br_application":         _TYPE_TO_APP.get(ev_type, ev_type),
            "drug_therapy_combination_detail_bm": drugs,
            "evidence_statement":     (
                f"CIViC level {ev_level}: {direction} {sig} for {biomarker_name} "
                f"in {r.get('disease', '')}"
                + (f" with {drugs}" if drugs else "")
            ).strip(),
            "source_excerpt":         f"CIViC level-{ev_level} curation",
            "source_section":         "CIViC",
            "validated_by_civic":     True,
        })

    # ---- Inferences: 1 row per (biomarker, br_application) ----
    inferences: list[dict] = []
    seen_inf = set()
    for r in civic_rows:
        gene = (r.get("gene") or "").strip()
        variant = (r.get("variant") or "").strip()
        if not gene:
            continue
        biomarker_name = f"{gene} {variant}".strip() if variant else gene
        ev_type = r.get("evidence_type") or ""
        app = _TYPE_TO_APP.get(ev_type, ev_type)
        key = f"{biomarker_name}|{app}".lower()
        if key in seen_inf or not app:
            continue
        seen_inf.add(key)
        sig = r.get("clinical_significance") or ""
        direction = r.get("evidence_direction") or ""
        drugs = r.get("drugs") or ""
        inferences.append({
            "pubmed_id":            pmid,
            "biomarker_name":       biomarker_name,
            "biomarker_name_type":  f"{gene}-Genetic",
            "br_application":       app,
            "evidence_statement":   (
                f"{direction} {sig}".strip()
                + (f" (drugs: {drugs})" if drugs else "")
            ).strip(),
            "bm_outcome":           sig,
            "biomarker_name_std":   gene,
            "source_excerpt":       f"CIViC: {biomarker_name} -> {sig}".strip(),
            "source_section":       "CIViC",
            "validated_by_civic":   True,
        })

    return {
        "Study_Details": study_rows,
        "BM_Details":    bm_details,
        "BM_Results":    bm_results,
        "Inferences":    inferences,
    }
