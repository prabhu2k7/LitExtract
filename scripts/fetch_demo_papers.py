"""Download a curated list of pharma-demo candidate PMIDs.

Uses the existing Europe PMC pipeline (scripts.goldset.pmc) to resolve
PMIDs -> PMCIDs, check OA status, and download via the EPMC ?pdf=render
endpoint with %PDF-magic-byte validation.

Out of 12-15 candidates we typically expect ~60-80% to actually be PMC-OA
(some land in paywalled journals). The script reports per-PMID status; you
keep what works and swap the rest.

    py -3.12 scripts/fetch_demo_papers.py
    py -3.12 scripts/fetch_demo_papers.py --pmids 34471143 36175523 ...
    py -3.12 scripts/fetch_demo_papers.py --out D:/dev/pubmed_files/demo_2026-05-08
"""
from __future__ import annotations
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.goldset.pmc import pmid_to_pmcid, check_oa, download_pdf  # noqa: E402


# Candidate pool, organised by pharma-relevant story.
# Each tuple: (pmid, slot_label, expected_journal, why_it_matters)
# This list is "best-effort" — some will fail OA check and we just skip them.
CANDIDATES: list[tuple[str, str, str, str]] = [
    # --- KRAS G12C inhibitors (sotorasib / adagrasib) -------------------
    ("36175523", "KRAS-G12C-NSCLC",   "Cancers",          "Adagrasib + cetuximab in KRAS-G12C colorectal"),
    ("35418514", "KRAS-G12C-NSCLC",   "Cancers (MDPI)",   "Sotorasib real-world evidence"),
    ("34471143", "KRAS-G12C-pan",     "NEJM-adjacent",    "Adagrasib first-in-human (may be paywalled)"),

    # --- HER2-low breast (trastuzumab deruxtecan / DESTINY-Breast04) ----
    ("36251512", "HER2-low-Breast",   "Front Oncol",      "T-DXd HER2-low real-world cohort"),
    ("36567569", "HER2-low-Breast",   "Cancers",          "HER2-low IHC reproducibility"),
    ("35608658", "HER2-low-Breast",   "NEJM",             "DESTINY-Breast04 (likely paywall)"),

    # --- ESR1 mutations / endocrine resistance --------------------------
    ("36251478", "ESR1-Breast",       "Front Oncol",      "ESR1 ctDNA prognostic in metastatic breast"),
    ("35977977", "ESR1-Breast",       "BMC Cancer",       "ESR1 mutation review and clinical implications"),

    # --- MSI-H pan-cancer (pembrolizumab tumour-agnostic) ---------------
    ("35896834", "MSI-H-pan",         "BMC Cancer",       "Pembrolizumab in MSI-H solid tumours real-world"),
    ("36057432", "MSI-H-pan",         "Cancers",          "MSI-H detection methods comparison"),

    # --- FGFR fusion in cholangiocarcinoma (pemigatinib / infigratinib) -
    ("35053389", "FGFR2-Cholangio",   "JCO Precis Oncol", "Pemigatinib FGFR2 fusion biomarker analysis"),
    ("34731073", "FGFR2-Cholangio",   "Cancers",          "FGFR alterations + targeted therapy in cholangio"),

    # --- Bonus: tissue-agnostic NTRK extension (larotrectinib ext) ------
    ("36251478", "NTRK-extend",       "Front Oncol",      "Larotrectinib long-term outcomes"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmids", nargs="*",
                    help="Override PMIDs (else uses built-in candidate list)")
    ap.add_argument("--out", type=Path,
                    help="Output folder (default D:/dev/pubmed_files/demo_<today>)")
    args = ap.parse_args()

    today_tag = date.today().isoformat()
    out_root = args.out or Path(f"D:/dev/pubmed_files/demo_{today_tag}")
    pdfs_dir = out_root / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    if args.pmids:
        targets = [(p, "user-provided", "?", "") for p in args.pmids]
    else:
        targets = CANDIDATES

    pmids = [t[0] for t in targets]
    print(f"=== Fetching {len(pmids)} demo paper candidates -> {out_root} ===\n")

    print("[1/3] PMID -> PMCID (NCBI ID converter) ...")
    pmid_to_pmcid_map = pmid_to_pmcid(pmids)
    no_pmcid = [p for p, mp in pmid_to_pmcid_map.items() if not mp]
    if no_pmcid:
        print(f"  {len(no_pmcid)} PMIDs have no PMCID (not in PMC at all): {no_pmcid}")
    print()

    print("[2/3] Checking OA + downloading via Europe PMC ...")
    results: list[dict] = []
    success = 0
    for pmid, slot, journal, why in targets:
        pmcid = pmid_to_pmcid_map.get(pmid) or ""
        if not pmcid:
            print(f"  {pmid:10s} no PMCID")
            results.append({"pmid": pmid, "slot": slot, "journal": journal,
                            "pmcid": "", "license": "", "ok": False,
                            "error": "no_pmcid", "why": why})
            continue

        rec = check_oa(pmcid)
        rec.pmid = pmid
        if not rec.is_oa:
            print(f"  {pmid:10s} {pmcid:14s} NOT-OA  err={rec.error}")
            results.append({"pmid": pmid, "slot": slot, "journal": journal,
                            "pmcid": pmcid, "license": rec.license or "",
                            "ok": False, "error": f"not_oa: {rec.error}",
                            "why": why})
            continue

        path = download_pdf(rec, pdfs_dir)
        if path:
            size_kb = path.stat().st_size // 1024
            print(f"  {pmid:10s} {pmcid:14s} OK     {size_kb:>5} KB  license={rec.license}")
            results.append({"pmid": pmid, "slot": slot, "journal": journal,
                            "pmcid": pmcid, "license": rec.license or "",
                            "ok": True, "error": "", "why": why,
                            "size_kb": size_kb,
                            "pdf": str(path)})
            success += 1
        else:
            print(f"  {pmid:10s} {pmcid:14s} FAIL   err={rec.error}")
            results.append({"pmid": pmid, "slot": slot, "journal": journal,
                            "pmcid": pmcid, "license": rec.license or "",
                            "ok": False, "error": rec.error or "download_failed",
                            "why": why})

    print()
    print("[3/3] Writing manifest ...")
    manifest_path = out_root / "manifest.csv"
    fieldnames = ["pmid", "slot", "journal", "pmcid", "license",
                  "ok", "size_kb", "error", "why", "pdf"]
    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"  Saved: {manifest_path}")
    print()
    print("=" * 70)
    print(f"DONE. {success}/{len(targets)} PDFs downloaded -> {pdfs_dir}")
    print(f"      Folder ready for upload via the LitExtract UI.")
    print("=" * 70)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
