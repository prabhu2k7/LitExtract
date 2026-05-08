"""Validation data layer for the public benchmark page.

Reads:
  - <validation_dir>/goldset.xlsx           (CIViC-derived gold)
  - <validation_dir>/manifest.csv           (paper metadata + slot label)
  - <validation_dir>/goldset_civic_raw.tsv  (raw CIViC, for audit links)
  - biomarker-cl-out.xlsx                   (cached extractor output)
  - <validation_dir>/validation_history.json (version timeline)

Exposes pure functions that produce JSON-serialisable dicts. No DB calls.
"""
from __future__ import annotations
import io
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

import config
from verification_agent import (
    VerificationAgent,
    _normalize_biomarker_name,
)
from excel_handler import load_paper_from_output


VALIDATION_DIR = Path(os.getenv(
    "VALIDATION_DIR",
    "D:/dev/pubmed_files/showcase_10",
))


_SLOT_LABELS: dict[str, str] = {
    "EGFR":         "EGFR-NSCLC",
    "BRAF":         "BRAF",
    "KRAS":         "KRAS",
    "ERBB2":        "HER2-Breast",
    "BRCA1|BRCA2":  "BRCA1/2-Ovarian",
    "BRAF|KRAS|PIK3CA": "BRAF/KRAS/PIK3CA-CRC",
    "KEAP1|NQO1":   "KEAP1-NSCLC",
    "ABL1|BCR::ABL1": "BCR-ABL1-CML",
    "EML4::NTRK3|LMNA::NTRK1|NTRK3": "NTRK-fusion",
    "IDH1|IDH2":    "IDH1-AML",
}


def _slot_for(genes: str, diseases: str) -> str:
    if genes in _SLOT_LABELS:
        return _SLOT_LABELS[genes]
    short_disease = (diseases.split("|")[0] or "").strip()
    short_gene    = (genes.split("|")[0] or "").strip()
    return f"{short_gene}-{short_disease}" if short_gene else short_disease


@lru_cache(maxsize=1)
def _load_manifest() -> pd.DataFrame:
    p = VALIDATION_DIR / "manifest.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, dtype=str).fillna("")
    df["pmid"] = df["pmid"].astype(str)
    df["slot"] = df.apply(lambda r: _slot_for(r.get("genes", ""), r.get("diseases", "")), axis=1)
    return df


@lru_cache(maxsize=1)
def _load_goldset() -> dict[str, pd.DataFrame]:
    p = VALIDATION_DIR / "goldset.xlsx"
    if not p.exists():
        return {}
    return pd.read_excel(p, sheet_name=None)


@lru_cache(maxsize=1)
def _load_civic_raw() -> pd.DataFrame:
    p = VALIDATION_DIR / "goldset_civic_raw.tsv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, sep="\t", dtype=str).fillna("")
    if "pmid" in df.columns:
        df["pmid"] = df["pmid"].astype(str)
    return df


def _civic_links_for(pmid: str) -> list[dict[str, str]]:
    """Distinct CIViC molecular profiles cited in this paper, with verify URLs."""
    df = _load_civic_raw()
    if df.empty or "pmid" not in df.columns:
        return []
    sub = df[df["pmid"] == str(pmid)]
    if sub.empty:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, r in sub.iterrows():
        mp = (r.get("molecular_profile") or "").strip()
        url = (r.get("molecular_profile_civic_url") or "").strip()
        if mp and mp not in seen:
            seen.add(mp)
            out.append({
                "molecular_profile": mp,
                "civic_url":         url,
                "disease":           (r.get("disease") or "").strip(),
                "therapies":         (r.get("therapies") or r.get("drugs") or "").strip(),
                "evidence_level":    (r.get("evidence_level") or "").strip(),
                "significance":      (r.get("significance") or
                                      r.get("clinical_significance") or "").strip(),
            })
    return out


def _gold_for(pmid: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for name, df in _load_goldset().items():
        if df.empty:
            out[name] = []
            continue
        sub = df[df["pubmed_id"].astype(str) == str(pmid)]
        out[name] = sub.fillna("").to_dict(orient="records")
    return out


def _verifier_for(pmid: str) -> dict[str, Any] | None:
    """Run VerificationAgent for one paper. None if no cache."""
    extracted = load_paper_from_output(pmid)
    if not any(extracted.get(k) for k in
               ("Study_Details", "BM_Details", "BM_Results", "Inferences")):
        return None
    return VerificationAgent().verify(pmid, extracted, _gold_for(pmid))


def _badge_for(canon: float, missed: list[str]) -> str:
    if canon >= 100:
        return "perfect"
    if canon >= 80:
        return "high"
    if canon >= 50:
        return "partial"
    return "miss"


def get_summary() -> dict[str, Any]:
    """Aggregate scores + per-paper rows for the headline table."""
    manifest = _load_manifest()
    if manifest.empty:
        return {
            "aggregate": None,
            "papers": [],
            "validation_dir": str(VALIDATION_DIR),
            "available": False,
        }

    rows: list[dict[str, Any]] = []
    canon_vals: list[float] = []
    f1_vals: list[float] = []
    for _, m in manifest.iterrows():
        pmid = m["pmid"]
        v = _verifier_for(pmid)
        if v is None:
            rows.append({
                "pmid": pmid,
                "slot": m["slot"],
                "diseases": m.get("diseases", ""),
                "genes": m.get("genes", ""),
                "pmcid": m.get("pmcid", ""),
                "license": m.get("license", ""),
                "civic_evidence_count": int(m.get("civic_evidence_count") or 0),
                "extracted_total": 0,
                "gold_total": 0,
                "canonical_recall": None,
                "canonical_missed": [],
                "canonical_captured": [],
                "f1": None,
                "row_recall": None,
                "field_precision": None,
                "status": "no_extraction",
                "extraction_cached": False,
            })
            continue
        canon = float(v.get("Canonical_Biomarker_Recall") or 0.0)
        f1    = float(v.get("F1") or 0.0)
        canon_vals.append(canon)
        f1_vals.append(f1)
        ext = load_paper_from_output(pmid)
        gold = _gold_for(pmid)
        rows.append({
            "pmid": pmid,
            "slot": m["slot"],
            "diseases": m.get("diseases", ""),
            "genes": m.get("genes", ""),
            "pmcid": m.get("pmcid", ""),
            "license": m.get("license", ""),
            "civic_evidence_count": int(m.get("civic_evidence_count") or 0),
            "extracted_total": sum(len(ext.get(s, []))
                                   for s in ("Study_Details", "BM_Details",
                                             "BM_Results", "Inferences")),
            "gold_total": sum(len(gold.get(s, []))
                              for s in ("BM_Details", "BM_Results", "Inferences")),
            "canonical_recall":   round(canon, 1),
            "canonical_missed":   v.get("Canonical_Missed", []),
            "canonical_captured": v.get("Canonical_Captured", []),
            "f1":               round(f1, 1),
            "row_recall":       round(float(v.get("Row_Recall") or 0), 1),
            "field_precision":  round(float(v.get("Field_Precision") or 0), 1),
            "status":           _badge_for(canon, v.get("Canonical_Missed", [])),
            "extraction_cached": True,
        })

    # Aggregate stats over scored papers only (skip no_extraction)
    n = len(canon_vals)
    if n:
        s = sorted(canon_vals)
        median_canon = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        s2 = sorted(f1_vals)
        median_f1 = s2[n // 2] if n % 2 else (s2[n // 2 - 1] + s2[n // 2]) / 2
        agg = {
            "papers_total":          len(rows),
            "papers_scored":         n,
            "papers_at_100_canon":   sum(1 for x in canon_vals if x >= 100),
            "papers_at_95_canon":    sum(1 for x in canon_vals if x >= 95),
            "papers_at_80_canon":    sum(1 for x in canon_vals if x >= 80),
            "median_canonical":      round(median_canon, 1),
            "mean_canonical":        round(sum(canon_vals) / n, 1),
            "median_f1":             round(median_f1, 1),
            "mean_f1":                round(sum(f1_vals) / n, 1),
            "max_f1":                round(max(f1_vals), 1),
        }
    else:
        agg = None

    return {
        "aggregate": agg,
        "papers": rows,
        "validation_dir": str(VALIDATION_DIR),
        "available": True,
    }


def get_history() -> dict[str, Any]:
    p = VALIDATION_DIR / "validation_history.json"
    if not p.exists():
        return {"versions": [], "available": False}
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {"versions": data.get("versions", []), "available": True}


def _flat_rows(sheets: dict[str, list[dict]],
               sheet_filter: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sh in sheet_filter:
        for r in sheets.get(sh) or []:
            bm_raw = r.get("biomarker_name", "") or ""
            out.append({
                "sheet": sh,
                "biomarker_raw":        bm_raw,
                "biomarker_normalized": _normalize_biomarker_name(bm_raw),
                "disease":              r.get("disease", "") or r.get("disease_name", "") or "",
                "therapy":              r.get("therapy", "") or r.get("therapies", "") or "",
                "significance":         r.get("significance", "") or "",
                "outcome":              r.get("outcome_name", "") or "",
                "p_value":              r.get("p_value", "") or "",
                "br_application":       r.get("br_application", "") or "",
                # Audit trail — verbatim span from the PDF + section label.
                # Gold (CIViC) won't have these; only our extraction does.
                "source_excerpt":       (r.get("source_excerpt") or "").strip(),
                "source_section":       (r.get("source_section") or "").strip(),
            })
    return out


def get_paper_detail(pmid: str) -> dict[str, Any]:
    """Side-by-side gold vs extracted for one paper, plus match map."""
    pmid = str(pmid).strip()
    manifest = _load_manifest()
    meta = manifest[manifest["pmid"] == pmid].head(1)
    if meta.empty:
        return {"error": "pmid_not_in_manifest"}

    m = meta.iloc[0].to_dict()
    pmcid = (m.get("pmcid") or "").strip()
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/" if pmcid else ""

    extracted = load_paper_from_output(pmid)
    gold = _gold_for(pmid)

    SHEETS = ("BM_Details", "BM_Results", "Inferences")
    gold_rows = _flat_rows(gold, SHEETS)
    ext_rows  = _flat_rows(extracted, SHEETS)

    gold_set = {r["biomarker_normalized"] for r in gold_rows if r["biomarker_normalized"]}
    ext_set  = {r["biomarker_normalized"] for r in ext_rows  if r["biomarker_normalized"]}

    captured = sorted(gold_set & ext_set)
    missed   = sorted(gold_set - ext_set)
    extras   = sorted(ext_set - gold_set)

    v = _verifier_for(pmid)
    scores = None
    if v is not None:
        scores = {
            "canonical_recall": round(float(v.get("Canonical_Biomarker_Recall") or 0), 1),
            "f1":               round(float(v.get("F1") or 0), 1),
            "row_recall":       round(float(v.get("Row_Recall") or 0), 1),
            "field_precision":  round(float(v.get("Field_Precision") or 0), 1),
            "study_results":    round(float(v.get("Study_Results") or 0), 1),
            "bm_details":       round(float(v.get("BM_Details") or 0), 1),
            "bm_results":       round(float(v.get("BM_Results") or 0), 1),
            "inferences":       round(float(v.get("Inferences") or 0), 1),
        }

    return {
        "pmid":          pmid,
        "pmcid":         pmcid,
        "slot":          m.get("slot", ""),
        "diseases":      m.get("diseases", ""),
        "genes":         m.get("genes", ""),
        "pubmed_url":    pubmed_url,
        "pmc_url":       pmc_url,
        "civic_evidence_count": int(m.get("civic_evidence_count") or 0),
        "civic_profiles": _civic_links_for(pmid),
        "gold":          gold_rows,
        "extracted":     ext_rows,
        "canonical": {
            "gold":     sorted(gold_set),
            "ext":      sorted(ext_set),
            "captured": captured,
            "missed":   missed,
            "extras":   extras,
        },
        "scores": scores,
        "extraction_cached": v is not None,
    }


def build_paper_xlsx(pmid: str) -> bytes | None:
    """Auditable validation pack — one Excel file with 4 sheets:

      Summary       — paper metadata + scores
      Gold_CIViC    — gold rows (with normalized biomarker)
      Extracted     — our extraction (with normalized biomarker)
      Canonical     — gene-level pivot: was each gold biomarker captured?

    Returns the .xlsx bytes, or None if the PMID is unknown.
    """
    detail = get_paper_detail(pmid)
    if detail.get("error"):
        return None

    summary_rows = [
        ("PMID",                       detail.get("pmid", "")),
        ("Slot",                       detail.get("slot", "")),
        ("Disease (CIViC)",            detail.get("diseases", "")),
        ("Genes (CIViC)",              detail.get("genes", "")),
        ("PubMed URL",                 detail.get("pubmed_url", "")),
        ("PMC fulltext",               detail.get("pmc_url", "")),
        ("CIViC evidence rows",        detail.get("civic_evidence_count", 0)),
        ("",                           ""),
        ("Canonical Biomarker Recall", f"{detail['scores']['canonical_recall']:.1f}%"
                                       if detail.get("scores") else "n/a"),
        ("Full F1",                    f"{detail['scores']['f1']:.1f}"
                                       if detail.get("scores") else "n/a"),
        ("Row Recall",                 f"{detail['scores']['row_recall']:.1f}%"
                                       if detail.get("scores") else "n/a"),
        ("Field Precision",            f"{detail['scores']['field_precision']:.1f}%"
                                       if detail.get("scores") else "n/a"),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["Field", "Value"])

    gold_df = pd.DataFrame(detail.get("gold", []))
    ext_df  = pd.DataFrame(detail.get("extracted", []))

    canon = detail.get("canonical", {})
    canon_rows: list[dict[str, Any]] = []
    for g in canon.get("gold", []):
        canon_rows.append({
            "biomarker_normalized": g,
            "in_gold":              True,
            "in_extracted":         g in canon.get("ext", []),
            "status":               "captured" if g in canon.get("captured", [])
                                                else "missed",
        })
    for e in canon.get("ext", []):
        if e not in canon.get("gold", []):
            canon_rows.append({
                "biomarker_normalized": e,
                "in_gold":              False,
                "in_extracted":         True,
                "status":               "extra (not in CIViC gold)",
            })
    canon_df = pd.DataFrame(canon_rows)

    civic_df = pd.DataFrame(detail.get("civic_profiles", []))

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary_df.to_excel(w, sheet_name="Summary", index=False)
        canon_df.to_excel(w,   sheet_name="Canonical_Match", index=False)
        gold_df.to_excel(w,    sheet_name="Gold_CIViC", index=False)
        ext_df.to_excel(w,     sheet_name="Extracted", index=False)
        if not civic_df.empty:
            civic_df.to_excel(w, sheet_name="CIViC_Profile_Links", index=False)
    return buf.getvalue()


def build_summary_xlsx() -> bytes:
    """All-papers benchmark export — 1 sheet of per-paper metrics + 1 sheet
    of version history. Used as a single shareable file for pharma."""
    s = get_summary()
    h = get_history()

    papers_df = pd.DataFrame(s.get("papers", []))
    if not papers_df.empty:
        papers_df["canonical_missed"]   = papers_df["canonical_missed"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else v)
        papers_df["canonical_captured"] = papers_df["canonical_captured"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else v)

    agg = s.get("aggregate") or {}
    agg_rows = [(k, v) for k, v in agg.items()] if agg else []
    agg_df = pd.DataFrame(agg_rows, columns=["metric", "value"])

    versions_df = pd.DataFrame(h.get("versions", []))
    if not versions_df.empty:
        versions_df["changes"] = versions_df["changes"].apply(
            lambda v: " | ".join(v) if isinstance(v, list) else v)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        agg_df.to_excel(w,      sheet_name="Aggregate", index=False)
        papers_df.to_excel(w,   sheet_name="Per_Paper", index=False)
        versions_df.to_excel(w, sheet_name="Version_History", index=False)
    return buf.getvalue()
