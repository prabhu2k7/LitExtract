"""Extract every PDF in a goldset folder + score against the gold.

Walks `<out_dir>/pdfs/*.pdf`, runs each through `pipeline_local`
(gpt-4o-mini default), then scores the extraction against the rows in
`<out_dir>/goldset.xlsx` for the same PMID.

Output:
  - extractions land in biomarker-cl-out.xlsx (the canonical workbook
    used by the rest of the pipeline) and in `runs_openai`/`uploads` DB
  - a comparison report file at `<out_dir>/baseline_report.txt`
  - per-paper F1 summary printed to stdout

Usage:
    python scripts/run_baseline.py D:/dev/pubmed_files/showcase_10

Cost: ~$0.02 per paper (gpt-4o-mini). 10 papers ≈ $0.20.
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from typing import Any

# Make repo root importable
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

from pipeline_local import LocalExtractionPipeline  # noqa: E402
from verification_agent import VerificationAgent  # noqa: E402
from column_mappings import SHEET_COLUMNS  # noqa: E402
import config  # noqa: E402


# Force UTF-8 stdout on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("goldset_dir", type=Path,
                    help="Folder containing pdfs/ subfolder + goldset.xlsx")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only run the first N papers (for testing)")
    args = ap.parse_args()

    pdfs_dir = args.goldset_dir / "pdfs"
    goldset_xlsx = args.goldset_dir / "goldset.xlsx"
    if not pdfs_dir.exists() or not goldset_xlsx.exists():
        print(f"ERROR: missing {pdfs_dir} or {goldset_xlsx}")
        return 1

    pdfs = sorted(pdfs_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]

    print(f"Goldset: {args.goldset_dir}")
    print(f"PDFs   : {len(pdfs)} to extract")
    print(f"Model  : {config.active_model_name()}  (provider={config.LLM_PROVIDER})")
    print()

    # Load gold once
    gold_sheets = pd.read_excel(goldset_xlsx, sheet_name=None)

    pipeline = LocalExtractionPipeline()  # uses .env OPENAI_API_KEY
    verifier = VerificationAgent()

    rows = []
    total_cost = 0.0
    t_total = time.time()

    for i, pdf in enumerate(pdfs, 1):
        pmid = pdf.stem
        print(f"[{i}/{len(pdfs)}] {pmid}  ({pdf.stat().st_size/1024:.0f} KB)")
        t0 = time.time()
        try:
            result = pipeline.process_pdf(pdf, paper_id=pmid)
        except Exception as e:
            print(f"      EXTRACTION FAILED: {type(e).__name__}: {e}")
            rows.append({"pmid": pmid, "error": str(e)[:200]})
            continue

        elapsed = time.time() - t0
        cost = (result.get("cost") or {}).get("cost_usd", 0.0)
        total_cost += cost
        counts = result.get("counts", {})

        # Score against gold
        gold_for_pmid = {}
        for name, df in gold_sheets.items():
            if df.empty:
                gold_for_pmid[name] = []
            else:
                sub = df[df["pubmed_id"].astype(str) == str(pmid)]
                gold_for_pmid[name] = sub.fillna("").to_dict(orient="records")

        try:
            verification = verifier.verify(pmid, result["extracted"], gold_for_pmid)
        except Exception as e:
            print(f"      VERIFICATION FAILED: {type(e).__name__}: {e}")
            verification = {}

        f1 = verification.get("F1") or 0
        recall = verification.get("Row_Recall") or 0
        precision = verification.get("Field_Precision") or 0

        print(f"      extracted: study={counts.get('Study_Details',0)} bmd={counts.get('BM_Details',0)} bmr={counts.get('BM_Results',0)} inf={counts.get('Inferences',0)}")
        print(f"      F1={f1:.1f}  Recall={recall:.1f}  Precision={precision:.1f}  cost=${cost:.4f}  time={elapsed:.0f}s")

        rows.append({
            "pmid":    pmid,
            "F1":       round(f1, 1),
            "Recall":   round(recall, 1),
            "Precision": round(precision, 1),
            "Study_Results": round(verification.get("Study_Results") or 0, 1),
            "BM_Details":    round(verification.get("BM_Details") or 0, 1),
            "BM_Results":    round(verification.get("BM_Results") or 0, 1),
            "Inferences":    round(verification.get("Inferences") or 0, 1),
            "ext_study":  counts.get("Study_Details", 0),
            "ext_bmd":    counts.get("BM_Details", 0),
            "ext_bmr":    counts.get("BM_Results", 0),
            "ext_inf":    counts.get("Inferences", 0),
            "gold_bmd":   len(gold_for_pmid.get("BM_Details") or []),
            "gold_bmr":   len(gold_for_pmid.get("BM_Results") or []),
            "gold_inf":   len(gold_for_pmid.get("Inferences") or []),
            "cost_usd":   round(cost, 4),
            "time_s":     round(elapsed, 0),
        })

    elapsed_total = time.time() - t_total

    # Summary
    print()
    print("=" * 80)
    print(f"BASELINE COMPLETE  ·  {len(rows)} papers  ·  total cost ${total_cost:.4f}  ·  {elapsed_total/60:.1f} min")
    print("=" * 80)
    df = pd.DataFrame(rows)
    if not df.empty and "F1" in df.columns:
        ok = df.dropna(subset=["F1"])
        if len(ok):
            print(f"  Median F1: {ok['F1'].median():.1f}")
            print(f"  Mean   F1: {ok['F1'].mean():.1f}")
            print(f"  Min    F1: {ok['F1'].min():.1f}")
            print(f"  Max    F1: {ok['F1'].max():.1f}")
            print(f"  Above 70%: {(ok['F1'] >= 70).sum()} / {len(ok)}")
            print(f"  Above 95%: {(ok['F1'] >= 95).sum()} / {len(ok)}")
    print()

    # Write detailed report
    report_path = args.goldset_dir / "baseline_report.csv"
    df.to_csv(report_path, index=False)
    print(f"Detailed report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
