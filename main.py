"""Top-level orchestrator: load -> classify -> extract -> verify -> persist."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any

import config
import init_db
from llm_wrapper import get_llm
from document_loader import load_document
from study_classifier import classify
from prompt_composer import get_prompt_hash
from agents import (
    StudyDetailsAgent,
    BMDetailsAgent,
    BMResultsAgent,
    InferencesAgent,
)
from verification_agent import VerificationAgent
from excel_handler import upsert_paper, load_gold_for_paper
from token_tracker import tracker


class BiomarkerExtractionPipeline:
    def __init__(self) -> None:
        init_db.init_db()
        self.llm = get_llm()
        self.study_agent   = StudyDetailsAgent(self.llm)
        self.bm_det_agent  = BMDetailsAgent(self.llm)
        self.bm_res_agent  = BMResultsAgent(self.llm)
        self.infer_agent   = InferencesAgent(self.llm)
        self.verifier      = VerificationAgent()

    def process_paper(self, pubmed_id: str,
                       force_rerun: bool = False) -> dict[str, Any]:
        tracker.reset()
        run_id = f"{pubmed_id}_{uuid.uuid4().hex[:8]}"
        run_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        document = load_document(pubmed_id)
        text = document.get("text_data", "")
        tables_text = document.get("structured_tables_text", "")

        classification = classify(text, tables_text)
        prompt_context = {
            "disease":     classification["disease"],
            "study_types": classification["study_types"],
            "bm_types":    classification["bm_types"],
        }

        study_rows   = self.study_agent.extract(pubmed_id, document, prompt_context)
        bm_det_rows  = self.bm_det_agent.extract(pubmed_id, document, prompt_context)

        biomarker_names = [
            (r.get("biomarker_name") or "").strip()
            for r in bm_det_rows if r.get("biomarker_name")
        ]

        bm_res_rows = self.bm_res_agent.extract(
            pubmed_id, document, biomarker_names, prompt_context
        )
        infer_rows = self.infer_agent.extract(
            pubmed_id, document, biomarker_names, bm_det_rows, prompt_context
        )

        extracted = {
            "Study_Details": study_rows,
            "BM_Details":    bm_det_rows,
            "BM_Results":    bm_res_rows,
            "Inferences":    infer_rows,
        }
        upsert_paper(pubmed_id, extracted)

        gold = load_gold_for_paper(pubmed_id)
        verification = self.verifier.verify(pubmed_id, extracted, gold)

        totals = tracker.get_totals()
        model_name = config.active_model_name()

        scores_row = {
            "run_id":         run_id,
            "run_datetime":   run_dt,
            "prompt_version": get_prompt_hash(
                classification["disease"],
                classification["study_types"],
                classification["bm_types"],
            ),
            "prompt_hash":    get_prompt_hash(
                classification["disease"],
                classification["study_types"],
                classification["bm_types"],
            ),
            "study_types":    classification["study_types"],
            "bm_types":       classification["bm_types"],
            "disease":        classification["disease"],
            "confidence":     classification["confidence_level"],
            "confidence_reason": f"disease_score={classification['disease_confidence']}",
            "F1":             verification["F1"],
            "Row_Recall":     verification["Row_Recall"],
            "Field_Precision": verification["Field_Precision"],
            "Study_Results":  verification["Study_Results"],
            "BM_Details":     verification["BM_Details"],
            "BM_Results":     verification["BM_Results"],
            "Inferences":     verification["Inferences"],
            "extraction_input_tokens":  totals["input_tokens"],
            "extraction_output_tokens": totals["output_tokens"],
            "extraction_total_tokens":  totals["total_tokens"],
            "extraction_cost_usd":      totals["cost_usd"],
            "cost_usd_per_paper":       totals["cost_usd"],
            "study_details_count":  len(study_rows),
            "bm_details_count":     len(bm_det_rows),
            "bm_results_count":     len(bm_res_rows),
            "inferences_count":     len(infer_rows),
            "gold_bm_results_count": len(gold.get("BM_Results") or []),
        }
        init_db.insert_benchmark_row(pubmed_id, scores_row, model_name)
        init_db.upsert_extraction_log(pubmed_id, run_id, {
            "run_datetime": run_dt,
            "model": model_name,
            "disease": classification["disease"],
            "study_types": classification["study_types"],
            "bm_types": classification["bm_types"],
            "cost_usd": totals["cost_usd"],
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
        })

        self._print_summary(pubmed_id, scores_row, totals)

        return {
            "pubmed_id":  pubmed_id,
            "run_id":     run_id,
            "scores":     scores_row,
            "extracted":  extracted,
            "gold":       gold,
            "verification": verification,
            "classification": classification,
            "cost":       totals,
        }

    def verify_only(self, pubmed_id: str) -> dict[str, Any]:
        from excel_handler import load_paper_from_output
        extracted = load_paper_from_output(pubmed_id)
        gold = load_gold_for_paper(pubmed_id)
        verification = self.verifier.verify(pubmed_id, extracted, gold)
        return {"pubmed_id": pubmed_id, "verification": verification}

    def _print_summary(self, pubmed_id: str, scores: dict, totals: dict) -> None:
        print(
            f"[{pubmed_id}] F1={scores['F1']:.1f}  "
            f"Recall={scores['Row_Recall']:.1f}  "
            f"Precision={scores['Field_Precision']:.1f}  "
            f"cost=${totals['cost_usd']:.4f}  "
            f"bm_details={scores['bm_details_count']}  "
            f"bm_results={scores['bm_results_count']}"
        )
