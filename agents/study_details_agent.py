"""Study-level metadata extractor. Single-pass."""
from __future__ import annotations
import re

from .base_agent import BaseExtractionAgent


_INSTITUTION_REGION = [
    (r"\bchina\b|\bchinese\b", "China"),
    (r"\bindia\b|\bindian\b", "India"),
    (r"\busa\b|\bunited states\b|\bamerica\b", "USA"),
    (r"\bjapan\b|\bjapanese\b", "Japan"),
    (r"\bkorea\b|\bkorean\b", "South Korea"),
    (r"\bgermany\b|\bgerman\b", "Germany"),
    (r"\bitaly\b|\bitalian\b", "Italy"),
    (r"\bfrance\b|\bfrench\b", "France"),
    (r"\bspain\b|\bspanish\b", "Spain"),
    (r"\buk\b|\bunited kingdom\b|\bbritain\b", "UK"),
]


class StudyDetailsAgent(BaseExtractionAgent):
    agent_name = "study_details"

    def extract(self, pubmed_id, document_data, prompt_context):
        rows = super().extract(pubmed_id, document_data, prompt_context)
        return [self._postprocess(r, document_data) for r in rows]

    def _postprocess(self, row: dict, document_data: dict) -> dict:
        text = (document_data.get("text_data") or "").lower()

        if not row.get("geographical_region"):
            for pat, region in _INSTITUTION_REGION:
                if re.search(pat, text):
                    row["geographical_region"] = region
                    break

        if not row.get("gender_distribution"):
            row["gender_distribution"] = "Balanced"

        if not row.get("number_of_arms"):
            arms = 0
            if row.get("study_arm1_description"):
                arms += 1
            if row.get("study_arm2_description"):
                arms += 1
            if arms:
                row["number_of_arms"] = arms

        return row
