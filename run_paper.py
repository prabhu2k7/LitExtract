"""CLI: python run_paper.py <PMID> [--force] [--verify-only]"""
from __future__ import annotations
import argparse
import sys

from main import BiomarkerExtractionPipeline


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("pmid", help="PubMed ID")
    p.add_argument("--force", action="store_true", help="Force re-extraction")
    p.add_argument("--verify-only", action="store_true",
                   help="Score existing output without calling the LLM")
    args = p.parse_args()

    pipeline = BiomarkerExtractionPipeline()
    if args.verify_only:
        result = pipeline.verify_only(args.pmid)
        v = result["verification"]
        print(
            f"[{args.pmid}] VERIFY-ONLY  F1={v['F1']:.1f}  "
            f"Recall={v['Row_Recall']:.1f}  Precision={v['Field_Precision']:.1f}"
        )
        return 0

    pipeline.process_paper(args.pmid, force_rerun=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
