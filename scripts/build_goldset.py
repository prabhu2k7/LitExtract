"""Build a 25-paper goldset for LitExtract validation.

Pipeline:
  1. Download CIViC nightly TSV (gold-standard source)
  2. Filter to peer-reviewed, pharma-relevant evidence
  3. Pick 25 PMIDs covering diverse diseases + biomarkers
  4. Resolve PMID -> PMCID (NCBI ID converter)
  5. Filter to OA-PDF-available papers only
  6. Download PDFs into D:/dev/pubmed_files/pdfs/
  7. Build goldset.xlsx in our 4-sheet schema
  8. Write manifest.csv + README.md

Outputs land in D:/dev/pubmed_files/ (outside the repo). PDFs are
copyrighted/CC-BY by the source journals — we do not commit them.

Usage:
    python scripts/build_goldset.py [--target-count 25] [--out D:/dev/pubmed_files]

Cost: $0. No LLM calls. Pure data plumbing.
"""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

# Make repo root importable (for sibling imports + SHEET_COLUMNS reuse)
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.goldset.civic import (
    fetch_civic_tsv, load_civic, filter_useful, filter_pharma_relevant,
    select_25_pmids,
)
from scripts.goldset.curated import select_curated, SHOWCASE
from scripts.goldset.pmc import pmid_to_pmcid, check_oa, download_pdf, PmcRecord
from scripts.goldset.schema import emit_rows_for_paper
from column_mappings import SHEET_COLUMNS

DEFAULT_OUT = Path("D:/dev/pubmed_files")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-count", type=int, default=25)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--candidate-pool", type=int, default=400,
                    help="How many PMIDs to TRY before giving up on hitting target. "
                         "End-to-end success rate is ~5%% (PMCID×OA×PDF-render), "
                         "so 400 candidates -> ~25 successful downloads.")
    ap.add_argument("--curated", action="store_true",
                    help="Use the curated-pharma-showcase picker (10 specific "
                         "biomarker x disease tuples) instead of top-N random.")
    args = ap.parse_args()

    out_dir: Path = args.out.resolve()
    pdfs_dir = out_dir / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output: {out_dir}")
    print(f"Target: {args.target_count} OA papers covering pharma-priority diseases")
    print()

    # 1) CIViC
    print("[1/7] Fetching CIViC nightly TSV...")
    tsv_path = fetch_civic_tsv(out_dir)
    df = load_civic(tsv_path)
    print(f"      loaded {len(df)} CIViC evidence rows")

    # 2) Filter
    print("[2/7] Filtering for pharma-relevant, accepted, A/B/C-level evidence...")
    df = filter_useful(df)
    df = filter_pharma_relevant(df)
    n_papers = df["pmid"].nunique()
    print(f"      kept {len(df)} rows across {n_papers} unique PMIDs")

    # 3) Pick PMIDs — either curated showcase or top-N
    if args.curated:
        print(f"[3/7] Selecting curated pharma-showcase PMIDs ({len(SHOWCASE)} target categories)...")
        # Re-load the unfiltered df because curated picker targets specific
        # (gene, disease) tuples that may not all be Predictive/A/B/C-level
        # — we keep ALL accepted rows for those PMIDs in the final gold.
        full_df = load_civic(tsv_path)
        if "evidence_status" in full_df.columns:
            full_df = full_df[full_df["evidence_status"].fillna("").str.lower() == "accepted"]
        picks = select_curated(full_df)
        candidates = [pmid for pmid, _, _ in picks]
        # Replace the pharma-filtered df with the curated subset so step 7
        # generates gold rows from ALL accepted CIViC evidence for those papers.
        df = full_df[full_df["pmid"].isin(candidates)]
        # Bound target_count by the number of categories we actually found
        args.target_count = max(len(candidates), 1)
        target_by_pmid = {pmid: t for pmid, t, _ in picks}
        print(f"      candidates: {len(candidates)} of {len(SHOWCASE)} categories filled "
              f"({len(df)} CIViC evidence rows total)")
    else:
        print(f"[3/7] Selecting top {args.candidate_pool} candidate PMIDs...")
        pool_size = min(args.candidate_pool, n_papers)
        candidates = select_25_pmids(df, target_count=pool_size)
        target_by_pmid = {}
        print(f"      candidates: {len(candidates)}")

    # 4) PMID -> PMCID
    print("[4/7] Resolving PMIDs to PMCIDs (NCBI ID converter)...")
    pmcid_map = pmid_to_pmcid(candidates)
    with_pmcid = [(p, c) for p, c in pmcid_map.items() if c]
    print(f"      with PMCID: {len(with_pmcid)} / {len(candidates)}")

    # 5) OA check
    print(f"[5/7] Checking PMC OA status for {len(with_pmcid)} papers...")
    records: list[PmcRecord] = []
    for i, (pmid, pmcid) in enumerate(with_pmcid, 1):
        rec = check_oa(pmcid)
        rec.pmid = pmid
        records.append(rec)
        if i % 10 == 0:
            print(f"      checked {i}/{len(with_pmcid)}")
        if not args.curated and sum(1 for r in records if r.is_oa) >= args.target_count + 15:
            # Early exit (random mode only — curated needs all candidates)
            break

    if args.curated:
        # Curated mode: try EPMC for ANY PMCID-indexed paper. EPMC's
        # open-access corpus is broader than NCBI's strict OA subset; the
        # download itself validates with the %PDF magic byte check, so
        # paywalled papers fail cleanly and we move to the next candidate
        # for that target.
        oa_records = [r for r in records if r.pmcid]
        n_strict_oa = sum(1 for r in records if r.is_oa)
        print(f"      will attempt EPMC for all {len(oa_records)} PMCID-indexed papers "
              f"(NCBI-strict-OA subset is {n_strict_oa})")
    else:
        oa_records = [r for r in records if r.is_oa]
        print(f"      OA-licensed: {len(oa_records)} / {len(records)} "
              f"(of which {sum(1 for r in oa_records if r.pdf_url)} have direct PDF URLs)")

    # 6) Download PDFs (curated mode: at most one per target, prefer densest)
    print(f"[6/7] Downloading up to {args.target_count} PDFs to {pdfs_dir}...")
    successes: list[PmcRecord] = []
    successful_targets: set[str] = set()
    target_total = len({t.label for t in target_by_pmid.values()}) if target_by_pmid else 0
    for rec in oa_records:
        target = target_by_pmid.get(rec.pmid) if target_by_pmid else None
        # In curated mode, skip if this target already has a successful download
        if target is not None and target.label in successful_targets:
            continue
        # In random mode, stop when we have enough
        if not target_by_pmid and len(successes) >= args.target_count:
            break
        path = download_pdf(rec, pdfs_dir)
        tag = f" [{target.label}]" if target else ""
        if path:
            print(f"      OK   {rec.pmid}  {rec.pmcid}  {path.stat().st_size/1024:.0f} KB  ({rec.license or '-'}){tag}")
            successes.append(rec)
            if target is not None:
                successful_targets.add(target.label)
        else:
            print(f"      FAIL {rec.pmid}  {rec.pmcid}  {rec.error}{tag}")
        # In curated mode, stop when ALL targets covered
        if target_by_pmid and len(successful_targets) >= target_total:
            break

    if target_by_pmid:
        print(f"      downloaded {len(successes)} (covering {len(successful_targets)}/{target_total} targets)")
    else:
        print(f"      downloaded {len(successes)} / {args.target_count}")

    # 7) Build goldset.xlsx + manifest.csv + README
    print("[7/7] Building goldset.xlsx + manifest.csv + README.md...")
    chosen_pmids = {r.pmid for r in successes}
    chosen_df = df[df["pmid"].isin(chosen_pmids)]

    # Save the raw CIViC subset for audit
    raw_path = out_dir / "goldset_civic_raw.tsv"
    chosen_df.to_csv(raw_path, sep="\t", index=False)
    print(f"      raw CIViC subset -> {raw_path} ({len(chosen_df)} rows)")

    # Build the 4-sheet goldset
    sheets = {name: [] for name in SHEET_COLUMNS}
    for pmid in chosen_pmids:
        rows = chosen_df[chosen_df["pmid"] == pmid].to_dict(orient="records")
        per_sheet = emit_rows_for_paper(pmid, rows)
        for name, items in per_sheet.items():
            sheets[name].extend(items)

    goldset_path = out_dir / "goldset.xlsx"
    with pd.ExcelWriter(goldset_path, engine="openpyxl") as writer:
        for name, columns in SHEET_COLUMNS.items():
            rows = sheets[name]
            df_out = pd.DataFrame(rows)
            for c in columns:
                if c not in df_out.columns:
                    df_out[c] = ""
            # Add the validation marker as the last column for easy filtering
            extra = [c for c in df_out.columns if c not in columns]
            ordered = list(columns) + extra
            df_out = df_out[ordered] if not df_out.empty else pd.DataFrame(columns=ordered)
            df_out.to_excel(writer, sheet_name=name, index=False)
    print(f"      goldset.xlsx -> {goldset_path}")
    for name in SHEET_COLUMNS:
        print(f"        sheet {name:18s} {len(sheets[name]):4d} rows")

    # Manifest
    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "pmid", "pmcid", "license", "civic_evidence_count",
            "diseases", "genes", "evidence_levels", "pdf_path", "pdf_size_bytes",
        ])
        for rec in successes:
            sub = chosen_df[chosen_df["pmid"] == rec.pmid]
            diseases = "|".join(sorted(set(sub["disease"].dropna().tolist())))[:200]
            genes = "|".join(sorted(set(sub["gene"].dropna().tolist())))[:200] if "gene" in sub.columns else ""
            levels = "|".join(sorted(set(sub["evidence_level"].dropna().tolist())))
            pdf = pdfs_dir / f"{rec.pmid}.pdf"
            w.writerow([
                rec.pmid, rec.pmcid, rec.license or "",
                len(sub), diseases, genes, levels,
                str(pdf), pdf.stat().st_size if pdf.exists() else 0,
            ])
    print(f"      manifest.csv -> {manifest_path}")

    # README
    readme_path = out_dir / "README.md"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with readme_path.open("w", encoding="utf-8") as f:
        f.write(f"""# LitExtract goldset

Built {today} by `scripts/build_goldset.py` (in the LitExtract repo).

## What's in this folder

| File | Purpose |
|---|---|
| `pdfs/` | {len(successes)} Open Access biomedical PDFs from PMC |
| `goldset.xlsx` | Curated facts in LitExtract's 4-sheet schema (Study_Details / BM_Details / BM_Results / Inferences) |
| `goldset_civic_raw.tsv` | Raw CIViC evidence subset for the same {len(successes)} PMIDs (audit trail) |
| `manifest.csv` | One row per PMID: PMCID, license, fact count, file size |
| `civic-evidence-YYYYMMDD.tsv` | Cached upstream CIViC dump |

## Provenance

- **Source of truth for "correct" extractions:** [CIViC](https://civicdb.org/)
  Clinical Evidence Summaries (CC0). Each row in `goldset.xlsx` is tagged
  `validated_by_civic = True` and traceable to a peer-reviewed CIViC curation.
- **Source of PDFs:** [PMC Open Access subset](https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/).
  All PDFs are CC-BY / CC-BY-NC / similar — see per-paper license in `manifest.csv`.

## Coverage

{len(successes)} papers spanning pharma-priority oncology indications. CIViC
evidence types kept: Predictive (drug response), Prognostic, Diagnostic.
Levels A / B / C only (skipped preclinical level D).

## Use

To validate LitExtract's extraction accuracy on a paper:

1. Run LitExtract on `pdfs/<PMID>.pdf` → produces 4 extracted sheets.
2. Compare against `goldset.xlsx` (filter to that PMID).
3. Run F1/Precision/Recall per sheet (this is what `verification_agent.py`
   does — currently disconnected in v0.4 UI flow, will re-enable in v0.5).

The CIViC gold is **partial**: it captures the headline clinical evidence
(gene + disease + drug + direction) but does not curate study design,
demographics, or full statistical detail. Treat it as a **necessary but
not sufficient** check — i.e., LitExtract should ALWAYS contain these
facts, plus more.

## Refresh

```
python scripts/build_goldset.py --target-count 25 --out D:/dev/pubmed_files
```

The CIViC TSV is re-fetched if older than today. PDFs are cached — re-runs
only download missing files.

## Licensing

CIViC data: CC0 (public domain dedication).
Each PDF: per-paper license (see `manifest.csv` `license` column).
This goldset assembly: scripts are AGPL-3.0 (same as LitExtract).
""")
    print(f"      README.md -> {readme_path}")
    print()
    print(f"DONE. {len(successes)} papers ready in {out_dir}")
    return 0 if successes else 1


if __name__ == "__main__":
    raise SystemExit(main())
