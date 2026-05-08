"""Re-score baseline extractions against gold WITHOUT re-running extraction.

Loads extractions from biomarker-cl-out.xlsx (cached by pipeline_local) and
runs them through the (updated) VerificationAgent against goldset.xlsx.

Use after editing verification_agent.py / column_mappings.py to evaluate
how a normaliser change affects F1, at $0 cost.

    python scripts/rescore_baseline.py D:/dev/pubmed_files/showcase_10
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

from verification_agent import VerificationAgent  # noqa: E402
from excel_handler import load_paper_from_output  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("goldset_dir", type=Path)
    args = ap.parse_args()

    pdfs_dir = args.goldset_dir / "pdfs"
    goldset_xlsx = args.goldset_dir / "goldset.xlsx"
    if not goldset_xlsx.exists():
        print(f"ERROR: missing {goldset_xlsx}")
        return 1

    manifest_path = args.goldset_dir / "manifest.csv"
    if manifest_path.exists():
        pmids = pd.read_csv(manifest_path, dtype=str)["pmid"].tolist()
    else:
        pmids = [p.stem for p in sorted(pdfs_dir.glob("*.pdf"))]
    gold_sheets = pd.read_excel(goldset_xlsx, sheet_name=None)
    verifier = VerificationAgent()

    rows = []
    for pmid in pmids:
        extracted = load_paper_from_output(pmid)
        if not any(extracted.get(k) for k in ("Study_Details", "BM_Details", "BM_Results", "Inferences")):
            print(f"  {pmid:12s} no cached extraction")
            continue
        gold_for_pmid = {}
        for name, df in gold_sheets.items():
            if df.empty:
                gold_for_pmid[name] = []
                continue
            sub = df[df["pubmed_id"].astype(str) == str(pmid)]
            gold_for_pmid[name] = sub.fillna("").to_dict(orient="records")
        v = verifier.verify(pmid, extracted, gold_for_pmid)
        f1 = v.get("F1", 0)
        recall = v.get("Row_Recall", 0)
        precision = v.get("Field_Precision", 0)
        canon = v.get("Canonical_Biomarker_Recall", 0)
        missed = v.get("Canonical_Missed", [])
        bmd = v.get("BM_Details", 0)
        bmr = v.get("BM_Results", 0)
        inf = v.get("Inferences", 0)
        std = v.get("Study_Results", 0)
        ext_n = sum(len(extracted.get(s, [])) for s in ("Study_Details", "BM_Details", "BM_Results", "Inferences"))
        gold_n = sum(len(gold_for_pmid.get(s, [])) for s in ("BM_Details", "BM_Results", "Inferences"))
        miss_str = (", missed=" + ",".join(missed)) if missed else ""
        print(f"  {pmid:12s}  Canon={canon:5.1f}  F1={f1:5.1f}  R={recall:5.1f}  P={precision:5.1f}  | "
              f"bmd={bmd:5.1f}  bmr={bmr:5.1f}  inf={inf:5.1f}  | "
              f"ext={ext_n:3d}  gold={gold_n:3d}{miss_str}")
        rows.append({"pmid": pmid, "Canonical_Biomarker_Recall": canon,
                      "F1": f1, "Row_Recall": recall,
                      "Field_Precision": precision,
                      "Study_Results": std, "BM_Details": bmd,
                      "BM_Results": bmr, "Inferences": inf,
                      "ext_n": ext_n, "gold_n": gold_n,
                      "canonical_missed": ";".join(missed)})

    if not rows:
        print("No cached extractions found.")
        return 1

    df = pd.DataFrame(rows)
    print()
    print("=" * 80)
    print(f"RESCORE  ·  {len(rows)} papers")
    print("=" * 80)
    print(f"  Canonical Biomarker Recall (PHARMA HEADLINE)")
    print(f"     Median: {df['Canonical_Biomarker_Recall'].median():.1f}%")
    print(f"     Mean:   {df['Canonical_Biomarker_Recall'].mean():.1f}%")
    print(f"     ==100%: {(df['Canonical_Biomarker_Recall'] >= 100).sum()} / {len(df)}")
    print(f"     >= 95%: {(df['Canonical_Biomarker_Recall'] >= 95).sum()} / {len(df)}")
    print(f"     >= 80%: {(df['Canonical_Biomarker_Recall'] >= 80).sum()} / {len(df)}")
    print()
    print(f"  Full F1 (32-field strict)")
    print(f"     Median: {df['F1'].median():.1f}")
    print(f"     Mean:   {df['F1'].mean():.1f}")
    print(f"     Max:    {df['F1'].max():.1f}")
    print(f"     >= 50%: {(df['F1'] >= 50).sum()} / {len(df)}")
    print(f"     >= 70%: {(df['F1'] >= 70).sum()} / {len(df)}")
    print(f"     >= 95%: {(df['F1'] >= 95).sum()} / {len(df)}")

    out = args.goldset_dir / "rescore_report.csv"
    df.to_csv(out, index=False)
    print(f"  Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
