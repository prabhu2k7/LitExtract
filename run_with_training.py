"""Batch runner with optional training loop and deferred mode."""
from __future__ import annotations
import argparse
from collections import defaultdict

import config
from main import BiomarkerExtractionPipeline
from training_loop import TrainingLoop
from llm_wrapper import get_llm
from verification_agent import VerificationAgent


def _resolve_pmids(args) -> list[str]:
    if args.papers:
        return args.papers
    if args.batch2:
        return config.BATCH2_PUBMED_IDS
    if args.batch3:
        return config.BATCH3_PUBMED_IDS
    if args.batch4:
        return config.BATCH4_PUBMED_IDS
    return config.EXPECTED_PUBMED_IDS


def run_batch_deferred(pmids: list[str], max_cycles: int) -> None:
    pipeline = BiomarkerExtractionPipeline()

    # Phase 1: extract all papers once.
    results: dict[str, dict] = {}
    for pmid in pmids:
        try:
            results[pmid] = pipeline.process_paper(pmid, force_rerun=True)
        except Exception as exc:
            print(f"[{pmid}] FAILED in phase 1: {exc}")

    # Phase 2: group failures by disease.
    failures_by_disease: dict[str | None, list[str]] = defaultdict(list)
    for pmid, res in results.items():
        f1 = (res.get("scores") or {}).get("F1") or 0
        if f1 < config.TARGET_F1:
            disease = (res.get("classification") or {}).get("disease")
            failures_by_disease[disease].append(pmid)

    if not failures_by_disease:
        print("All papers met the F1 target. No training needed.")
        return

    # Phase 3: run the training loop per disease group.
    trainer = TrainingLoop(
        pipeline=pipeline,
        verification_agent=VerificationAgent(),
        llm=get_llm(),
        target_f1=config.TARGET_F1,
        max_cycles=max_cycles,
    )
    for disease, pmid_list in failures_by_disease.items():
        print(f"\n=== Training cycle for disease={disease} ({len(pmid_list)} papers) ===")
        for pmid in pmid_list:
            try:
                trainer.run(pmid, {})
            except Exception as exc:
                print(f"[{pmid}] training failed: {exc}")


def run_batch_inline(pmids: list[str], max_cycles: int) -> None:
    pipeline = BiomarkerExtractionPipeline()
    trainer = TrainingLoop(
        pipeline=pipeline,
        verification_agent=VerificationAgent(),
        llm=get_llm(),
        target_f1=config.TARGET_F1,
        max_cycles=max_cycles,
    )
    for pmid in pmids:
        try:
            trainer.run(pmid, {})
        except Exception as exc:
            print(f"[{pmid}] FAILED: {exc}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--papers", nargs="*", help="Explicit PMID list")
    p.add_argument("--batch2", action="store_true")
    p.add_argument("--batch3", action="store_true")
    p.add_argument("--batch4", action="store_true")
    p.add_argument("--deferred", action="store_true",
                   help="Phase 1 extract all, phase 2 group failures, phase 3 train per disease")
    p.add_argument("--max-cycles", type=int, default=config.MAX_TRAINING_CYCLES)
    args = p.parse_args()

    pmids = _resolve_pmids(args)
    if not pmids:
        print("No PMIDs resolved. Pass --papers <PMID...> or populate config.py batches.")
        return 1

    if args.deferred:
        run_batch_deferred(pmids, args.max_cycles)
    else:
        run_batch_inline(pmids, args.max_cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
