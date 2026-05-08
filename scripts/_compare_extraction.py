"""Side-by-side comparison: LitExtract output vs CIViC gold for one PMID."""
from __future__ import annotations
import sys
import json
import urllib.request
from pathlib import Path

import pandas as pd

# Windows console is cp1252 by default — force utf-8 so we can print box chars
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PMID = sys.argv[1] if len(sys.argv) > 1 else "15138475"
API = "http://127.0.0.1:8765"
GOLDSET = Path(r"D:/dev/pubmed_files/goldset.xlsx")


def main() -> None:
    # 1. Pull extracted result
    with urllib.request.urlopen(f"{API}/api/results/{PMID}") as r:
        res = json.loads(r.read())

    # 2. Pull gold-standard rows
    gold_sheets = pd.read_excel(GOLDSET, sheet_name=None)
    gold = {n: df[df["pubmed_id"].astype(str) == PMID] for n, df in gold_sheets.items()}

    # 3. Header
    cost = res["meta"].get("extraction_cost_usd") or 0
    duration_ms = res.get("duration_ms") or 0
    print("=" * 70)
    print(f'PAPER: {PMID} ({res.get("filename")})')
    print(f'Filename detected: pmid={res.get("pmid")} display_id={res.get("display_id")}')
    print(f'Classified disease: {res["meta"].get("disease")}')
    print(f'Cost: ${cost:.4f}    Duration: {duration_ms/1000:.1f}s')
    print("=" * 70)

    extracted = res.get("extracted", {})
    print()
    print(f"  {'SHEET':<18s} {'EXTRACTED':>10s} {'GOLD':>8s}")
    for sheet in ("Study_Details", "BM_Details", "BM_Results", "Inferences"):
        n_ext = len(extracted.get(sheet, []))
        n_gold = len(gold.get(sheet, pd.DataFrame()))
        print(f"  {sheet:<18s} {n_ext:>10d} {n_gold:>8d}")
    print()

    # 4. Extracted detail
    print("─" * 70)
    print("EXTRACTED — Study_Details")
    print("─" * 70)
    for r in extracted.get("Study_Details", []):
        for k in ("study_type", "disease_name", "patient_count",
                  "treatment_regimen", "geographical_region", "follow_up_duration"):
            v = r.get(k)
            if v not in (None, "", []):
                print(f"  {k:<25s} {v}")

    print()
    print("─" * 70)
    print(f'EXTRACTED — BM_Details ({len(extracted.get("BM_Details", []))} rows)')
    print("─" * 70)
    for r in extracted.get("BM_Details", []):
        n = r.get("biomarker_name") or ""
        t = r.get("biomarker_type") or ""
        nat = r.get("biomarker_nature") or ""
        print(f"  {n:<25s} type={t:<10s} nature={nat}")

    print()
    print("─" * 70)
    print(f'EXTRACTED — BM_Results ({len(extracted.get("BM_Results", []))} rows)')
    print("─" * 70)
    for r in extracted.get("BM_Results", []):
        bm = r.get("biomarker_name", "") or ""
        outcome = r.get("outcome_name", "") or ""
        vt = r.get("value_type", "") or ""
        rv = r.get("r_value", "") or ""
        p_pref = r.get("p_value_prefix", "") or ""
        p = r.get("p_value", "") or ""
        sig = r.get("significance_call", "") or ""
        app = r.get("br_application", "") or ""
        print(f"  {bm:<14s} outcome={outcome[:25]:<25s} {vt[:14]:<14s} {rv} p={p_pref}{p} {sig} ({app})")

    print()
    print("─" * 70)
    print(f'EXTRACTED — Inferences ({len(extracted.get("Inferences", []))} rows)')
    print("─" * 70)
    for r in extracted.get("Inferences", []):
        bm = r.get("biomarker_name") or ""
        app = r.get("br_application") or ""
        out = r.get("bm_outcome") or ""
        ev = (r.get("evidence_statement") or "")[:80]
        print(f"  {bm:<20s} {app:<12s} {out}")
        if ev:
            print(f"    evidence: {ev}")

    # 5. Gold side
    print()
    print("=" * 70)
    print("GOLD STANDARD (CIViC):")
    print("=" * 70)
    for sheet in ("BM_Details", "BM_Results", "Inferences"):
        df = gold.get(sheet, pd.DataFrame())
        if df.empty:
            continue
        print()
        print(f"--- GOLD {sheet} ({len(df)} rows) ---")
        if sheet == "BM_Details":
            cols = [c for c in ("biomarker_name", "biomarker_type",
                                "biomarker_nature", "biomarker_name_std") if c in df.columns]
        elif sheet == "BM_Results":
            cols = [c for c in ("biomarker_name", "disease_name",
                                "br_application", "bm_outcome_association",
                                "drug_therapy_combination_detail_bm",
                                "evidence_statement") if c in df.columns]
        else:
            cols = [c for c in ("biomarker_name", "br_application", "bm_outcome") if c in df.columns]
        if cols:
            print(df[cols].to_string(index=False, max_colwidth=70))

    # 6. Diff summary on biomarker names
    print()
    print("=" * 70)
    print("BIOMARKER NAME OVERLAP (case-insensitive substring match):")
    print("=" * 70)
    ext_bms = set()
    for r in extracted.get("BM_Details", []):
        ext_bms.add((r.get("biomarker_name") or "").upper().strip())
    gold_bms = set()
    gdf = gold.get("BM_Details", pd.DataFrame())
    for _, r in gdf.iterrows():
        gold_bms.add(str(r.get("biomarker_name") or "").upper().strip())
    gold_genes = set()
    for n in gold_bms:
        # CIViC gold names are like "CCND1 Amplification" — extract gene symbol
        gold_genes.add(n.split()[0] if n else "")
    print(f"  Extracted biomarkers: {sorted(b for b in ext_bms if b)}")
    print(f"  Gold biomarkers     : {sorted(b for b in gold_bms if b)}")
    print(f"  Gold gene symbols   : {sorted(g for g in gold_genes if g)}")

    # Match: did the extractor find any name containing the gold gene symbol?
    matched = []
    missed = []
    for g in gold_genes:
        if not g:
            continue
        if any(g in b for b in ext_bms):
            matched.append(g)
        else:
            missed.append(g)
    print()
    print(f"  ✓ matched: {matched}")
    print(f"  ✗ missed : {missed}")


if __name__ == "__main__":
    main()
