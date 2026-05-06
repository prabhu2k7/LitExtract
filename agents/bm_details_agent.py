"""Biomarker catalog extractor. Runs a gap-fill second pass if needed."""
from __future__ import annotations
import re

from .base_agent import BaseExtractionAgent


_DEFAULT_TYPE_NATURE = [
    (re.compile(r"^mi[rR]-?\d"),        "RNA",     "miRNA"),
    (re.compile(r"^let-?\d"),           "RNA",     "miRNA"),
    (re.compile(r"^linc\d|lncrna", re.I), "RNA",   "lncRNA"),
    (re.compile(r"^circ", re.I),        "RNA",     "circRNA"),
    (re.compile(r"^(nlr|plr|sii|lmr|mlr)$", re.I), "Protein", "Cellular Marker"),
    (re.compile(r"^cea$|^afp$|^psa$|^ca\d+", re.I), "Protein", "Tumor Marker"),
]

_GAP_MIN_BIOMARKERS = 8


class BMDetailsAgent(BaseExtractionAgent):
    agent_name = "bm_details"

    def extract(self, pubmed_id, document_data, prompt_context):
        first = super().extract(pubmed_id, document_data, prompt_context)
        first = self._normalize_bm_details_names(first)

        if len({r.get("biomarker_name", "").lower() for r in first}) < _GAP_MIN_BIOMARKERS:
            gap_doc = dict(document_data)
            gap_doc["_gap_fill_header"] = (
                "This appears to be an incomplete first pass "
                f"(fewer than {_GAP_MIN_BIOMARKERS} unique biomarkers). "
                "Scan the paper AGAIN and extract ANY biomarker you may have missed, "
                "especially those mentioned only in tables or supplementary text."
            )
            second = BaseExtractionAgent.extract(self, pubmed_id, gap_doc, prompt_context)
            second = self._normalize_bm_details_names(second)
            combined = first + second
        else:
            combined = first

        return self._deduplicate_rows(combined)

    # ---------- helpers ----------
    def _normalize_bm_details_names(self, rows: list[dict]) -> list[dict]:
        out: list[dict] = []
        for r in rows:
            name = (r.get("biomarker_name") or "").strip()
            if not name:
                continue
            name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
            r["biomarker_name"] = name
            if not r.get("biomarker_type") or not r.get("biomarker_nature"):
                for pat, ty, nat in _DEFAULT_TYPE_NATURE:
                    if pat.search(name):
                        r.setdefault("biomarker_type", ty)
                        r.setdefault("biomarker_nature", nat)
                        break
            out.append(r)
        return out

    def _deduplicate_rows(self, rows: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for r in rows:
            key = (r.get("biomarker_name") or "").strip().lower()
            key = re.sub(r"[\s\-_]+", "", key)
            if not key:
                continue
            if key not in seen:
                seen[key] = r
            else:
                for k, v in r.items():
                    if v and not seen[key].get(k):
                        seen[key][k] = v
        return list(seen.values())
