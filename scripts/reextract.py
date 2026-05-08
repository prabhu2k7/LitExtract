"""Re-extract a list of PMIDs through LocalExtractionPipeline.

Used to fill cache gaps in the showcase set. Writes to biomarker-cl-out.xlsx
and SQLite as a normal pipeline run would. Idempotent — calling twice for the
same PMID just overwrites the cache.

    py -3.12 scripts/reextract.py D:/dev/pubmed_files/showcase_10 31580757 22802530 34247201
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pipeline_local import LocalExtractionPipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs_root", type=Path,
                    help="Folder containing pdfs/<pmid>.pdf")
    ap.add_argument("pmids", nargs="+")
    args = ap.parse_args()

    pdfs_dir = args.pdfs_root / "pdfs"
    pipe = LocalExtractionPipeline()

    for pmid in args.pmids:
        pdf = pdfs_dir / f"{pmid}.pdf"
        if not pdf.exists():
            print(f"  {pmid}  MISSING PDF at {pdf}")
            continue

        def _cb(stage: str) -> None:
            print(f"    [{pmid}] {stage}", flush=True)

        print(f"--- {pmid} ({pdf.stat().st_size/1024:.0f} KB) ---")
        try:
            r = pipe.process_pdf(pdf, paper_id=pmid, stage_callback=_cb)
        except Exception as e:
            print(f"  {pmid}  FAILED: {e!r}")
            continue
        ext = r["extracted"]
        cost = r.get("token_totals", {}).get("cost_usd")
        n = {s: len(ext[s]) for s in ext}
        print(f"  {pmid}  rows: {n}  cost: ${cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
