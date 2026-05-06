"""Author-conclusion extractor. Parallel per biomarker."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from .base_agent import BaseExtractionAgent


class InferencesAgent(BaseExtractionAgent):
    agent_name = "inferences"
    max_iterations = 2

    def extract(self,
                pubmed_id: str,
                document_data: dict,
                biomarkers: list[str] | None = None,
                bm_details_rows: list[dict] | None = None,
                prompt_context: dict | None = None) -> list[dict]:
        prompt_context = prompt_context or {}
        biomarkers = [b for b in (biomarkers or []) if b]

        if not biomarkers:
            rows = super().extract(pubmed_id, document_data, prompt_context)
            return self._postprocess(rows, bm_details_rows or [])

        indexed: list[tuple[int, list[dict]]] = []
        workers = max(1, config.BM_RESULTS_PARALLEL_WORKERS)

        def _run_single(idx: int, bm: str) -> tuple[int, list[dict]]:
            doc = dict(document_data)
            doc["_gap_fill_header"] = (
                f"Extract author conclusions ONLY for biomarker: {bm}. "
                "One row per (biomarker, application)."
            )
            rows = super(InferencesAgent, self).extract(pubmed_id, doc, prompt_context)
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

        return self._postprocess(merged, bm_details_rows or [])

    def _postprocess(self, rows: list[dict], bm_details: list[dict]) -> list[dict]:
        name_type_nature = {}
        for r in bm_details:
            key = (r.get("biomarker_name") or "").strip().lower()
            if key:
                name_type_nature[key] = r.get("biomarker_name_type_nature") or ""

        for r in rows:
            key = (r.get("biomarker_name") or "").strip().lower()
            if key in name_type_nature and name_type_nature[key]:
                r["biomarker_name_type_nature"] = name_type_nature[key]

        seen = set()
        out: list[dict] = []
        for r in rows:
            key = (
                (r.get("biomarker_name") or "").strip().lower(),
                (r.get("br_application") or "").strip().lower(),
                (r.get("evidence_statement") or "").strip().lower()[:100],
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out
