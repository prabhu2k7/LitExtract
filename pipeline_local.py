"""UI-flow extraction pipeline — local PDF input, no verification.

Mirrors main.BiomarkerExtractionPipeline.process_paper but:
  - Reads PDFs from disk via pdf_extractor.load_document_local (no Azure DI).
  - Skips verification_agent (no goldset comparison in v1).
  - Still writes results to biomarker-cl-out.xlsx and SQLite for the UI history.

verification_agent.py and training_loop.py are intentionally NOT imported here —
they remain on disk and the batch flow (main.py) still uses them.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import config
import init_db
from llm_wrapper import get_llm
from pdf_extractor import load_document_local
from study_classifier import classify
from prompt_composer import get_prompt_hash
from agents import (
    StudyDetailsAgent,
    BMDetailsAgent,
    BMResultsAgent,
    InferencesAgent,
)
from excel_handler import upsert_paper, load_paper_from_output
from token_tracker import tracker


SHEET_ORDER = ("Study_Details", "BM_Details", "BM_Results", "Inferences")


# Sub-stages, in order. Percent is "typical share of total runtime" — used by
# the UI to render a smooth progress bar even though we don't know exact length.
PIPELINE_STAGES: tuple[tuple[str, int], ...] = (
    ("parsing_pdf",                  3),
    ("classifying",                  2),
    ("extracting_study_details",    15),
    ("extracting_bm_details",       15),
    ("extracting_bm_results",       35),
    ("extracting_inferences",       25),
    ("writing_excel",                5),
    ("done",                       100),
)


StageCallback = Callable[[str], None]


class LocalExtractionPipeline:
    """Single-paper local pipeline used by the FastAPI backend.

    Constructed per request when a user-supplied API key is in play. Cheap to
    create (~50ms) — agents only hold a reference to the LangChain client; no
    network calls happen until `process_pdf()` runs.

    `api_key`, when provided, overrides the config-level key for THIS pipeline
    instance only. It is never persisted, never logged, and goes out of scope
    when this object is garbage-collected.
    """

    def __init__(self, api_key: str | None = None) -> None:
        init_db.init_db()
        self.llm = get_llm(api_key=api_key)
        self.study_agent = StudyDetailsAgent(self.llm)
        self.bm_det_agent = BMDetailsAgent(self.llm)
        self.bm_res_agent = BMResultsAgent(self.llm)
        self.infer_agent = InferencesAgent(self.llm)

    def process_pdf(self,
                     pdf_path: str | Path,
                     paper_id: str | None = None,
                     stage_callback: StageCallback | None = None) -> dict[str, Any]:
        """Run a single PDF through the 4-agent pipeline.

        `stage_callback(stage_name)` fires at each sub-stage transition so the
        API can surface fine-grained progress to the UI. Failures inside the
        callback are swallowed — progress UI is non-critical.
        """
        def _cb(name: str) -> None:
            if stage_callback is not None:
                try:
                    stage_callback(name)
                except Exception:
                    pass

        tracker.reset()
        pdf_path = Path(pdf_path).resolve()
        if paper_id is None:
            paper_id = pdf_path.stem
        run_id = f"{paper_id}_{uuid.uuid4().hex[:8]}"
        run_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        _cb("parsing_pdf")
        document = load_document_local(pdf_path, pubmed_id=paper_id)
        text = document.get("text_data", "")
        tables_text = document.get("structured_tables_text", "")

        _cb("classifying")
        classification = classify(text, tables_text)
        prompt_context = {
            "disease": classification["disease"],
            "study_types": classification["study_types"],
            "bm_types": classification["bm_types"],
        }

        _cb("extracting_study_details")
        study_rows = self.study_agent.extract(paper_id, document, prompt_context)

        _cb("extracting_bm_details")
        bm_det_rows = self.bm_det_agent.extract(paper_id, document, prompt_context)

        biomarker_names = [
            (r.get("biomarker_name") or "").strip()
            for r in bm_det_rows if r.get("biomarker_name")
        ]

        _cb("extracting_bm_results")
        bm_res_rows = self.bm_res_agent.extract(
            paper_id, document, biomarker_names, prompt_context
        )

        _cb("extracting_inferences")
        infer_rows = self.infer_agent.extract(
            paper_id, document, biomarker_names, bm_det_rows, prompt_context
        )

        _cb("writing_excel")

        extracted = {
            "Study_Details": study_rows,
            "BM_Details":    bm_det_rows,
            "BM_Results":    bm_res_rows,
            "Inferences":    infer_rows,
        }
        upsert_paper(paper_id, extracted)

        totals = tracker.get_totals()
        model_name = config.active_model_name()
        prompt_hash = get_prompt_hash(
            classification["disease"],
            classification["study_types"],
            classification["bm_types"],
        )

        scores_row = {
            "run_id":            run_id,
            "run_datetime":      run_dt,
            "prompt_version":    prompt_hash,
            "prompt_hash":       prompt_hash,
            "study_types":       classification["study_types"],
            "bm_types":          classification["bm_types"],
            "disease":           classification["disease"],
            "confidence":        classification["confidence_level"],
            "confidence_reason": f"disease_score={classification['disease_confidence']}",
            # F1/Recall/Precision fields left null — verification skipped in v1.
            "F1":                None,
            "Row_Recall":        None,
            "Field_Precision":   None,
            "Study_Results":     None,
            "BM_Details":        None,
            "BM_Results":        None,
            "Inferences":        None,
            "extraction_input_tokens":  totals["input_tokens"],
            "extraction_output_tokens": totals["output_tokens"],
            "extraction_total_tokens":  totals["total_tokens"],
            "extraction_cost_usd":      totals["cost_usd"],
            "cost_usd_per_paper":       totals["cost_usd"],
            "study_details_count": len(study_rows),
            "bm_details_count":    len(bm_det_rows),
            "bm_results_count":    len(bm_res_rows),
            "inferences_count":    len(infer_rows),
            "gold_bm_results_count": None,
            "status":              "complete",
            "notes":               f"local_pdf={pdf_path.name}",
        }
        init_db.insert_benchmark_row(paper_id, scores_row, model_name)
        init_db.upsert_extraction_log(paper_id, run_id, {
            "run_datetime": run_dt,
            "model":        model_name,
            "disease":      classification["disease"],
            "study_types":  classification["study_types"],
            "bm_types":     classification["bm_types"],
            "cost_usd":     totals["cost_usd"],
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "notes":        f"local_pdf={pdf_path.name}",
        })

        return {
            "paper_id":       paper_id,
            "run_id":         run_id,
            "run_datetime":   run_dt,
            "model":          model_name,
            "classification": classification,
            "extracted":      extracted,
            "counts": {
                "Study_Details": len(study_rows),
                "BM_Details":    len(bm_det_rows),
                "BM_Results":    len(bm_res_rows),
                "Inferences":    len(infer_rows),
            },
            "cost":           totals,
            "source_pdf":     str(pdf_path),
        }


def load_extracted_for_paper(paper_id: str) -> dict[str, list[dict]]:
    """Read previously-extracted rows for a paper from the workbook."""
    return load_paper_from_output(paper_id)


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python pipeline_local.py <pdf_path> [paper_id]")
        sys.exit(1)
    pdf = sys.argv[1]
    pid = sys.argv[2] if len(sys.argv) > 2 else None
    pipeline = LocalExtractionPipeline()
    result = pipeline.process_pdf(pdf, paper_id=pid)
    print(json.dumps({
        "paper_id":       result["paper_id"],
        "run_id":         result["run_id"],
        "classification": result["classification"],
        "counts":         result["counts"],
        "cost":           result["cost"],
    }, indent=2, default=str))
