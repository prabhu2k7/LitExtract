"""Base class for the 4 extraction agents."""
from __future__ import annotations
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from prompt_composer import compose_prompt
from token_tracker import tracker


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.DOTALL)


class BaseExtractionAgent:
    agent_name: str = "base"
    max_iterations: int = 3
    pass_threshold: float = 75.0
    system_preamble: str = (
        "You are an expert biomedical data extractor. "
        "Return ONLY valid JSON. Never invent data. "
        "Use empty string for unknown fields."
    )

    def __init__(self, llm) -> None:
        self.llm = llm

    # ---------- main entry ----------
    def extract(self,
                pubmed_id: str,
                document_data: dict,
                prompt_context: dict) -> list[dict]:
        document_data = {**document_data, "pubmed_id": pubmed_id}
        disease = prompt_context.get("disease")
        study_types = prompt_context.get("study_types") or []
        bm_types = prompt_context.get("bm_types") or []

        best_result: list[dict] = []
        best_score = -1.0
        repair_hint = ""

        for it in range(self.max_iterations):
            doc_with_hint = dict(document_data)
            if repair_hint:
                doc_with_hint["_gap_fill_header"] = repair_hint

            prompt = compose_prompt(
                self.agent_name, disease, study_types, bm_types, doc_with_hint
            )
            raw = self._call_llm(prompt)
            try:
                result = self._parse_json_response(raw)
            except ValueError as e:
                repair_hint = f"Previous response was not valid JSON: {e}. Return a JSON array."
                continue

            score, feedback = self._internal_eval(result, document_data)
            if score > best_score:
                best_score = score
                best_result = result
            if score >= self.pass_threshold:
                return result
            repair_hint = self._generate_repair_context(result, feedback)

        return best_result

    # ---------- LLM I/O ----------
    def _call_llm(self, prompt: str) -> str:
        messages = [
            SystemMessage(content=self.system_preamble),
            HumanMessage(content=prompt),
        ]
        resp = self.llm.invoke(messages)
        text = resp.content if hasattr(resp, "content") else str(resp)

        usage = getattr(resp, "usage_metadata", None) or {}
        input_t = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        output_t = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        if not (input_t or output_t):
            response_metadata = getattr(resp, "response_metadata", {}) or {}
            tu = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
            input_t = tu.get("prompt_tokens", 0) or tu.get("input_tokens", 0)
            output_t = tu.get("completion_tokens", 0) or tu.get("output_tokens", 0)
        tracker.add(int(input_t or 0), int(output_t or 0))
        return text if isinstance(text, str) else str(text)

    # ---------- parsing ----------
    def _parse_json_response(self, response: str) -> list[dict]:
        if not response:
            return []

        text = response.strip()

        m = _JSON_BLOCK_RE.search(text)
        if m:
            text = m.group(1)

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    return [r for r in parsed if isinstance(r, dict)]
            except json.JSONDecodeError:
                pass

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(str(e))

        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)]
        if isinstance(parsed, dict):
            for key in ("rows", "results", "data", "items"):
                if key in parsed and isinstance(parsed[key], list):
                    return [r for r in parsed[key] if isinstance(r, dict)]
            return [parsed]
        return []

    # ---------- self-eval ----------
    def _internal_eval(self, result: list[dict],
                        document_data: dict) -> tuple[float, str]:
        if not result:
            return 0.0, "empty result"

        total_fields = 0
        filled_fields = 0
        for row in result:
            for _, v in row.items():
                total_fields += 1
                if v not in (None, "", [], {}):
                    filled_fields += 1
        completeness = (filled_fields / total_fields * 100) if total_fields else 0.0
        return completeness, f"completeness={completeness:.1f}%"

    def _generate_repair_context(self, result: list[dict], feedback: str) -> str:
        return (
            f"Previous extraction was incomplete ({feedback}). "
            "Look again and fill missing fields. Do NOT invent data."
        )
