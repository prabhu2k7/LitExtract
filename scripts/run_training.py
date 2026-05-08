"""Training-loop driver — iterate extract/score/improve until F1 >= target.

Wraps `LocalExtractionPipeline` + the existing prompt-addon generator from
`training_loop.py`. For each paper that scores below `--target-f1` (default 95):

  1. Identify the worst sheet
  2. Use gpt-4o-mini to write a GENERIC prompt addon (per the project's
     standing rule: never paper-specific)
  3. Append addon to prompts/diseases/<disease>/<agent>_addon.txt
  4. Re-extract this paper
  5. Re-score
  6. REGRESSION TEST: re-extract every prior accepted paper of the same
     disease; if any drops in F1 by more than --regression-tolerance,
     REVERT the addon
  7. Max --max-cycles per paper
  8. HARD COST CAP: --cost-cap (default $3) — abort training the moment
     cumulative cost exceeds it

Usage:
    python scripts/run_training.py D:/dev/pubmed_files/showcase_10 \
           --target-f1 95 --max-cycles 2 --cost-cap 3.00
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

# Make repo root importable
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from pipeline_local import LocalExtractionPipeline  # noqa: E402
from verification_agent import VerificationAgent  # noqa: E402
from llm_wrapper import get_llm  # noqa: E402
from token_tracker import tracker  # noqa: E402
import config  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


IMPROVEMENT_SYSTEM = (
    "You are a prompt engineer for a biomarker extraction pipeline. "
    "Given a failure analysis, output GENERIC rules (not paper-specific) "
    "that can be appended to a domain addon prompt to fix the failure class. "
    "Keep output under 15 lines. Markdown bullets only. "
    "NEVER reference a specific PubMed ID, patient ID, study name, or any "
    "paper-specific identifier. Rules must apply to ANY future paper of the "
    "same disease/study type."
)

SHEET_TO_AGENT = {
    "Study_Details": "study_details",
    "BM_Details":    "bm_details",
    "BM_Results":    "bm_results",
    "Inferences":    "inferences",
}


def _score_one(verifier: VerificationAgent, pmid: str, extracted: dict, gold: dict) -> dict:
    try:
        return verifier.verify(pmid, extracted, gold)
    except Exception as e:
        return {"F1": 0, "error": str(e)[:200]}


def _gold_for_pmid(gold_sheets: dict[str, pd.DataFrame], pmid: str) -> dict[str, list[dict]]:
    out = {}
    for name, df in gold_sheets.items():
        if df.empty:
            out[name] = []
            continue
        sub = df[df["pubmed_id"].astype(str) == str(pmid)]
        out[name] = sub.fillna("").to_dict(orient="records")
    return out


def _pick_worst_sheet(scores: dict) -> str:
    """Identify the sheet with the lowest F1 (skipping perfect/missing)."""
    order = [
        ("BM_Results",    float(scores.get("BM_Results")    or 0)),
        ("BM_Details",    float(scores.get("BM_Details")    or 0)),
        ("Inferences",    float(scores.get("Inferences")    or 0)),
        ("Study_Details", float(scores.get("Study_Results") or 0)),
    ]
    # Filter out 100% (no improvement possible) and skip 0% on empty sheets
    order = [(n, s) for n, s in order if 0 < s < 100]
    if not order:
        return "BM_Results"  # fallback
    order.sort(key=lambda t: t[1])
    return order[0][0]


def _generate_addon(llm, sheet: str, disease: str | None,
                    gold_rows: list[dict], extracted_rows: list[dict]) -> str:
    """LLM-driven prompt addon generator. Returns the addon text or empty string."""
    brief = {
        "sheet":          sheet,
        "disease":        disease,
        "n_gold":         len(gold_rows),
        "n_extracted":    len(extracted_rows),
        "gold_sample":    gold_rows[:5],
        "extracted_sample": extracted_rows[:5],
    }
    prompt = (
        f"Failure analysis for sheet `{sheet}`, disease=`{disease}`:\n\n"
        f"{json.dumps(brief, indent=2, default=str)}\n\n"
        "Write GENERIC bullet-point rules to append to the disease prompt-addon. "
        "Rules must apply to any future paper of this disease/biomarker class. "
        "NEVER mention specific PMIDs, biomarker names from these examples, or "
        "phrases unique to a single paper. Reason from the failure pattern, not "
        "the data."
    )
    try:
        resp = llm.invoke([
            SystemMessage(content=IMPROVEMENT_SYSTEM),
            HumanMessage(content=prompt),
        ])
    except Exception as e:
        print(f"      [addon-gen FAILED: {type(e).__name__}: {e}]")
        return ""
    usage = getattr(resp, "usage_metadata", None) or {}
    tracker.add(int(usage.get("input_tokens") or 0),
                int(usage.get("output_tokens") or 0))
    text = resp.content if hasattr(resp, "content") else str(resp)
    return text.strip() if isinstance(text, str) else ""


def _addon_path(sheet: str, disease: str | None) -> Path | None:
    if not disease:
        return None
    agent = SHEET_TO_AGENT.get(sheet, sheet.lower())
    return config.PROMPTS_DIR / "diseases" / disease / f"{agent}_addon.txt"


def _append_addon(addon_path: Path, addon_text: str) -> str:
    """Append addon_text to addon_path. Returns previous file content for revert."""
    addon_path.parent.mkdir(parents=True, exist_ok=True)
    prior = addon_path.read_text(encoding="utf-8") if addon_path.exists() else ""
    header = f"\n\n## Auto-generated training rule (training run)\n"
    addon_path.write_text(prior + header + addon_text + "\n", encoding="utf-8")
    return prior


def _revert_addon(addon_path: Path, prior_content: str) -> None:
    if prior_content:
        addon_path.write_text(prior_content, encoding="utf-8")
    else:
        try:
            addon_path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("goldset_dir", type=Path)
    ap.add_argument("--target-f1", type=float, default=95.0)
    ap.add_argument("--max-cycles", type=int, default=2)
    ap.add_argument("--cost-cap", type=float, default=3.00)
    ap.add_argument("--regression-tolerance", type=float, default=2.0,
                    help="Reject addon if any prior paper's F1 drops by more than this.")
    args = ap.parse_args()

    pdfs_dir = args.goldset_dir / "pdfs"
    goldset_xlsx = args.goldset_dir / "goldset.xlsx"
    if not (pdfs_dir.exists() and goldset_xlsx.exists()):
        print(f"ERROR: missing {pdfs_dir} or {goldset_xlsx}")
        return 1

    pdfs = sorted(pdfs_dir.glob("*.pdf"))
    print(f"Training run: {len(pdfs)} papers · target F1 = {args.target_f1}% · "
          f"max {args.max_cycles} cycles · cost cap ${args.cost_cap:.2f}")

    pipeline = LocalExtractionPipeline()
    verifier = VerificationAgent()
    llm = get_llm()
    gold_sheets = pd.read_excel(goldset_xlsx, sheet_name=None)

    cumulative_cost = 0.0
    accepted_addons: list[dict] = []
    cycle_log: list[dict] = []

    # Track the F1 each paper most-recently reached (for regression test)
    paper_f1: dict[str, float] = {}
    paper_disease: dict[str, str] = {}
    paper_extracted: dict[str, dict] = {}

    def extract_and_score(pmid: str, pdf: Path) -> tuple[float, dict, dict, float]:
        nonlocal cumulative_cost
        if cumulative_cost >= args.cost_cap:
            print(f"      [COST CAP HIT — skipping further extractions]")
            return 0.0, {}, {}, 0.0
        result = pipeline.process_pdf(pdf, paper_id=pmid)
        cost = (result.get("cost") or {}).get("cost_usd", 0.0)
        cumulative_cost += cost
        gold = _gold_for_pmid(gold_sheets, pmid)
        scores = _score_one(verifier, pmid, result["extracted"], gold)
        return float(scores.get("F1") or 0), scores, result["extracted"], cost

    # ---------- main loop ----------
    for i, pdf in enumerate(pdfs, 1):
        pmid = pdf.stem
        print()
        print(f"=== [{i}/{len(pdfs)}] {pmid}  ({pdf.stat().st_size/1024:.0f} KB) ===")
        if cumulative_cost >= args.cost_cap:
            print(f"      [COST CAP — skipping]")
            continue

        f1, scores, extracted, cost = extract_and_score(pmid, pdf)
        disease = scores.get("disease") or ""
        paper_extracted[pmid] = extracted
        paper_disease[pmid] = disease
        paper_f1[pmid] = f1
        print(f"      baseline F1={f1:.1f}  (BM_D={scores.get('BM_Details') or 0:.0f}  "
              f"BM_R={scores.get('BM_Results') or 0:.0f}  "
              f"Inf={scores.get('Inferences') or 0:.0f})  "
              f"cost=${cost:.4f}  cum=${cumulative_cost:.4f}")

        if f1 >= args.target_f1:
            print(f"      ✓ at/above target — no training needed")
            continue

        # Training cycles
        for cycle in range(args.max_cycles):
            if cumulative_cost >= args.cost_cap:
                break
            sheet = _pick_worst_sheet(scores)
            print(f"      cycle {cycle+1}/{args.max_cycles} — worst sheet: {sheet}")
            addon_path = _addon_path(sheet, disease)
            if addon_path is None:
                print("      [no disease classified — cannot place addon, skip]")
                break

            gold = _gold_for_pmid(gold_sheets, pmid)
            addon_text = _generate_addon(
                llm, sheet, disease,
                gold.get(sheet) or [],
                extracted.get(sheet) or [],
            )
            if not addon_text:
                print("      [empty addon, skip]")
                break

            prior_content = _append_addon(addon_path, addon_text)
            print(f"      addon written to {addon_path.relative_to(_REPO)} ({len(addon_text)} chars)")

            # Re-extract this paper
            new_f1, new_scores, new_extracted, retry_cost = extract_and_score(pmid, pdf)
            print(f"      retry F1={new_f1:.1f}  cost=${retry_cost:.4f}  cum=${cumulative_cost:.4f}")

            if new_f1 <= f1:
                _revert_addon(addon_path, prior_content)
                print(f"      ✗ no F1 gain — REVERTED addon")
                cycle_log.append({"pmid": pmid, "cycle": cycle+1, "sheet": sheet,
                                   "result": "reverted", "f1_before": f1, "f1_after": new_f1})
                break

            # Regression test: re-extract prior accepted papers of same disease
            regress_papers = [
                (p, paper_f1[p]) for p in paper_f1
                if p != pmid and paper_disease.get(p) == disease
            ]
            regress_ok = True
            if regress_papers:
                print(f"      regression-testing on {len(regress_papers)} prior {disease} paper(s)...")
                for p, prior_f1 in regress_papers:
                    if cumulative_cost >= args.cost_cap:
                        regress_ok = False
                        print(f"      [COST CAP — aborting regression test]")
                        break
                    p_pdf = pdfs_dir / f"{p}.pdf"
                    rgr_f1, _, _, _ = extract_and_score(p, p_pdf)
                    delta = rgr_f1 - prior_f1
                    print(f"        {p}: {prior_f1:.1f} -> {rgr_f1:.1f} (Δ {delta:+.1f})")
                    if delta < -args.regression_tolerance:
                        regress_ok = False
                        break
                    paper_f1[p] = rgr_f1  # update trailing F1

            if not regress_ok:
                _revert_addon(addon_path, prior_content)
                print(f"      ✗ regression detected — REVERTED addon")
                cycle_log.append({"pmid": pmid, "cycle": cycle+1, "sheet": sheet,
                                   "result": "reverted_regression",
                                   "f1_before": f1, "f1_after": new_f1})
                break

            # ACCEPT
            print(f"      ✓ ACCEPTED addon (F1 {f1:.1f} -> {new_f1:.1f}, no regression)")
            accepted_addons.append({"pmid": pmid, "sheet": sheet, "disease": disease,
                                     "f1_before": f1, "f1_after": new_f1,
                                     "addon_path": str(addon_path)})
            cycle_log.append({"pmid": pmid, "cycle": cycle+1, "sheet": sheet,
                               "result": "accepted",
                               "f1_before": f1, "f1_after": new_f1})
            f1, scores, extracted = new_f1, new_scores, new_extracted
            paper_f1[pmid] = f1
            paper_extracted[pmid] = extracted

            if f1 >= args.target_f1:
                print(f"      ✓ above target — done with this paper")
                break

    # ---------- summary ----------
    print()
    print("=" * 80)
    print(f"TRAINING COMPLETE  ·  cumulative cost ${cumulative_cost:.4f}")
    print("=" * 80)
    if paper_f1:
        ok = [v for v in paper_f1.values() if v > 0]
        if ok:
            print(f"  Median F1: {sorted(ok)[len(ok)//2]:.1f}")
            print(f"  Mean   F1: {sum(ok)/len(ok):.1f}")
            print(f"  ≥{args.target_f1:.0f}%: {sum(1 for v in ok if v >= args.target_f1)} / {len(ok)}")
            print(f"  ≥80%:  {sum(1 for v in ok if v >= 80)} / {len(ok)}")
            print(f"  ≥70%:  {sum(1 for v in ok if v >= 70)} / {len(ok)}")
    print(f"  Accepted addons: {len(accepted_addons)}")
    for a in accepted_addons:
        print(f"    {a['pmid']:10s} {a['sheet']:14s} F1 {a['f1_before']:.1f} -> {a['f1_after']:.1f}  ({a['addon_path']})")
    print()

    # Save report
    out_path = args.goldset_dir / "training_report.json"
    out_path.write_text(json.dumps({
        "cumulative_cost_usd": cumulative_cost,
        "paper_f1": paper_f1,
        "accepted_addons": accepted_addons,
        "cycle_log": cycle_log,
    }, indent=2, default=str), encoding="utf-8")
    print(f"  Report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
