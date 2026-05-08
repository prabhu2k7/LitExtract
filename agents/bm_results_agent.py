"""Statistical-results extractor. Parallel per biomarker (3 workers)."""
from __future__ import annotations
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from .base_agent import BaseExtractionAgent


_TEST_NORMALIZATION = {
    r"\buni(?:variate)?\s*cox\b":   "Univariate Analysis",
    r"\bmulti(?:variate)?\s*cox\b": "Multivariate Analysis",
    r"\blogistic regression\b":     "Logistic Regression",
    r"\bkaplan[- ]meier\b":         "Kaplan-Meier",
    r"\blog[- ]rank\b":             "Log-rank",
    r"\bchi[- ]square|χ2|x2\b":     "Chi-square",
    r"\bfisher(?:'s)? exact\b":     "Fisher exact",
    r"\bmann[- ]whitney\b":         "Mann-Whitney",
    r"\bstudent'?s? t[- ]test\b":   "Student's t-test",
}

_VALUE_TYPE_NORMALIZATION = {
    "hr": "hazard ratio",
    "or": "odds ratio",
    "rr": "relative risk",
    "auroc": "auc",
    "roc auc": "auc",
}


class BMResultsAgent(BaseExtractionAgent):
    agent_name = "bm_results"
    max_iterations = 2

    def extract(self,
                pubmed_id: str,
                document_data: dict,
                biomarkers: list[str] | None = None,
                prompt_context: dict | None = None) -> list[dict]:
        prompt_context = prompt_context or {}
        biomarkers = [b for b in (biomarkers or []) if b]

        if not biomarkers:
            rows = super().extract(pubmed_id, document_data, prompt_context)
            return self._deduplicate_rows(self._normalize_extracted_rows(rows))

        indexed: list[tuple[int, list[dict]]] = []
        workers = max(1, config.BM_RESULTS_PARALLEL_WORKERS)

        def _run_single(idx: int, bm: str) -> tuple[int, list[dict]]:
            doc = dict(document_data)
            doc["_gap_fill_header"] = (
                f"Focus this extraction ONLY on biomarker: {bm}. "
                "Return one row per (outcome, statistical_test, patient_group). "
                "Do not extract other biomarkers."
            )
            rows = super(BMResultsAgent, self).extract(pubmed_id, doc, prompt_context)
            for r in rows:
                if not r.get("biomarker_name"):
                    r["biomarker_name"] = bm
            return idx, rows

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_single, i, bm) for i, bm in enumerate(biomarkers)]
            for fut in as_completed(futures):
                indexed.append(fut.result())

        indexed.sort(key=lambda t: t[0])
        merged: list[dict] = []
        for _, rows in indexed:
            merged.extend(rows)

        merged = self._normalize_extracted_rows(merged)
        return self._deduplicate_rows(merged)

    # ---------- normalization ----------
    def _normalize_extracted_rows(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            vt = (r.get("value_type") or "").strip().lower()
            r["value_type"] = _VALUE_TYPE_NORMALIZATION.get(vt, vt)

            st = (r.get("statistical_test") or "").strip()
            for pat, repl in _TEST_NORMALIZATION.items():
                if re.search(pat, st, re.IGNORECASE):
                    r["statistical_test"] = repl
                    break

            # LLM may emit p_value as either a string ("p<0.05") or a raw
            # numeric (0.04). Coerce to string before any string-ops.
            p_val = r.get("p_value")
            p_raw = "" if p_val is None else str(p_val).strip()
            r["p_value"] = p_raw

            if not r.get("significance_call"):
                try:
                    if p_raw:
                        p_num = float(re.sub(r"[<>=]", "", p_raw))
                        r["significance_call"] = "significant" if p_num < 0.05 else "not significant"
                except ValueError:
                    pass

            if p_raw and not r.get("p_value_prefix"):
                m = re.match(r"([<>=])\s*(.*)", p_raw)
                if m:
                    r["p_value_prefix"] = m.group(1)
                    r["p_value"] = m.group(2)
        return rows

    def _deduplicate_rows(self, rows: list[dict]) -> list[dict]:
        seen = set()
        out: list[dict] = []
        for r in rows:
            key = (
                (r.get("biomarker_name") or "").strip().lower(),
                (r.get("outcome_name")   or "").strip().lower(),
                (r.get("statistical_test") or "").strip().lower(),
                (r.get("patient_stratification_criteria_results_bm") or "").strip().lower(),
                (r.get("p_value") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out
