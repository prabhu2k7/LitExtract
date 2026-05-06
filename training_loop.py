"""Self-improvement loop: extract -> verify -> improve prompts -> re-extract."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

import config
from token_tracker import tracker

IMPROVEMENT_SYSTEM = (
    "You are a prompt engineer for a biomarker extraction pipeline. "
    "Given a failure analysis, output GENERIC rules (not paper-specific) "
    "that can be appended to a domain addon prompt to fix the failure class. "
    "Keep output under 20 lines. Markdown bullets only."
)


class TrainingLoop:
    def __init__(self,
                 pipeline,
                 verification_agent,
                 llm,
                 target_f1: float = config.TARGET_F1,
                 max_cycles: int = config.MAX_TRAINING_CYCLES) -> None:
        self.pipeline = pipeline
        self.verifier = verification_agent
        self.llm = llm
        self.target_f1 = target_f1
        self.max_cycles = max_cycles

    def run(self, pubmed_id: str, document_data: dict) -> dict[str, Any]:
        best: dict[str, Any] = {}

        for cycle in range(self.max_cycles):
            result = self.pipeline.process_paper(pubmed_id, force_rerun=True)
            scores = result.get("scores") or {}
            f1 = float(scores.get("F1") or 0)

            if not best or f1 > float(best.get("scores", {}).get("F1") or 0):
                best = result

            if f1 >= self.target_f1:
                return result

            sheet = self._pick_target_sheet(scores)
            disease = scores.get("disease")
            improvement = self._generate_prompt_improvement(
                sheet=sheet,
                disease=disease,
                gold_rows=result.get("gold", {}).get(sheet) or [],
                extracted_rows=result.get("extracted", {}).get(sheet) or [],
                failure_type=self._failure_type(sheet, scores),
            )
            if improvement:
                self._append_to_addon(sheet, disease, improvement)

        return best

    # ---------- decisions ----------
    def _pick_target_sheet(self, scores: dict) -> str:
        bm_res = float(scores.get("BM_Results") or 0)
        bm_det = float(scores.get("BM_Details") or 0)
        field_precision = float(scores.get("Field_Precision") or 0)

        if bm_res < 50 and bm_det < 50:
            return "bm_details"
        if field_precision < 50:
            return "bm_results"

        order = [
            ("bm_results",    float(scores.get("BM_Results") or 0)),
            ("bm_details",    float(scores.get("BM_Details") or 0)),
            ("inferences",    float(scores.get("Inferences") or 0)),
            ("study_details", float(scores.get("Study_Results") or 0)),
        ]
        order.sort(key=lambda t: t[1])
        return order[0][0]

    def _failure_type(self, sheet: str, scores: dict) -> str:
        fp = float(scores.get("Field_Precision") or 0)
        rr = float(scores.get("Row_Recall") or 0)
        return "precision" if fp < rr else "recall"

    # ---------- LLM improvement ----------
    def _generate_prompt_improvement(self,
                                      sheet: str,
                                      disease: str | None,
                                      gold_rows: list[dict],
                                      extracted_rows: list[dict],
                                      failure_type: str) -> str:
        brief = {
            "sheet": sheet,
            "disease": disease,
            "failure_type": failure_type,
            "n_gold": len(gold_rows),
            "n_extracted": len(extracted_rows),
            "gold_sample": gold_rows[:5],
            "extracted_sample": extracted_rows[:5],
        }
        prompt = (
            f"Failure analysis:\n{json.dumps(brief, indent=2, default=str)}\n\n"
            f"Produce GENERIC rules to fix this {failure_type} failure for "
            f"sheet={sheet}. Rules must not mention any specific PMID or "
            "paper-specific text."
        )
        try:
            resp = self.llm.invoke([
                SystemMessage(content=IMPROVEMENT_SYSTEM),
                HumanMessage(content=prompt),
            ])
        except Exception:
            return ""

        usage = getattr(resp, "usage_metadata", None) or {}
        tracker.add(
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        return text.strip() if isinstance(text, str) else str(text)

    def _append_to_addon(self, sheet: str, disease: str | None, text: str) -> None:
        if not disease:
            return
        addon = config.PROMPTS_DIR / "diseases" / disease / f"{sheet}_addon.txt"
        addon.parent.mkdir(parents=True, exist_ok=True)
        header = "\n\n## Auto-generated training rules\n"
        existing = addon.read_text(encoding="utf-8") if addon.exists() else ""
        addon.write_text(existing + header + text + "\n", encoding="utf-8")
