"""Local PDF -> {text_data, table_data, structured_tables, structured_tables_text}.

Drop-in alternative to document_loader.load_document for the UI flow.
- Text + layout via pymupdf4llm (fast, returns clean markdown).
- Tables via pdfplumber (more reliable column detection than pymupdf).
- Output shape matches document_loader.load_document exactly so the rest of
  the pipeline (study_classifier, prompt_composer, agents, excel_handler)
  consumes it without modification.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pymupdf4llm
import pdfplumber

from table_parser import format_tables_for_llm


def _extract_text_markdown(pdf_path: Path) -> str:
    """Full-document markdown extraction via pymupdf4llm."""
    return pymupdf4llm.to_markdown(str(pdf_path)) or ""


def _extract_tables_pdfplumber(pdf_path: Path) -> list[dict]:
    """Page-by-page table extraction; returns table_parser-compatible dicts."""
    tables: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                page_tables = page.extract_tables() or []
            except Exception:
                page_tables = []
            for t_idx, raw in enumerate(page_tables, start=1):
                if not raw or len(raw) < 2:
                    continue
                headers = [_clean_cell(c) for c in raw[0]]
                rows = [[_clean_cell(c) for c in row] for row in raw[1:]]
                rows = [r for r in rows if any(c for c in r)]
                if not rows:
                    continue
                tables.append({
                    "context": f"Page {page_idx} Table {t_idx}",
                    "headers": headers,
                    "rows": rows,
                })
    return tables


def _clean_cell(val: Any) -> str:
    if val is None:
        return ""
    return " ".join(str(val).split())


def _tables_to_markdown(tables: list[dict]) -> str:
    """Render tables as plain markdown — kept for parity with the DI flow's table_data."""
    if not tables:
        return ""
    blocks: list[str] = []
    for t in tables:
        ctx = t.get("context") or ""
        headers = t.get("headers") or []
        rows = t.get("rows") or []
        if not headers and rows:
            headers = [f"Col{i+1}" for i in range(len(rows[0]))]
        if ctx:
            blocks.append(ctx)
        blocks.append("| " + " | ".join(headers) + " |")
        blocks.append("|" + "|".join(["---"] * len(headers)) + "|")
        for row in rows:
            cells = list(row) + [""] * max(0, len(headers) - len(row))
            blocks.append("| " + " | ".join(cells[: len(headers)]) + " |")
        blocks.append("")
    return "\n".join(blocks)


def load_document_local(pdf_path: str | Path,
                        pubmed_id: str | None = None) -> dict[str, Any]:
    """Load a local PDF and return the same dict shape as document_loader.load_document.

    Args:
        pdf_path: filesystem path to a PDF
        pubmed_id: optional identifier; defaults to the filename stem
    """
    p = Path(pdf_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {p}")
    if pubmed_id is None:
        pubmed_id = p.stem

    text = _extract_text_markdown(p)
    structured = _extract_tables_pdfplumber(p)
    tables_md = _tables_to_markdown(structured)

    return {
        "pubmed_id": pubmed_id,
        "text_data": text,
        "table_data": tables_md,
        "structured_tables": structured,
        "structured_tables_text": format_tables_for_llm(structured),
        "source_pdf": str(p),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pdf_extractor.py <pdf_path>")
        sys.exit(1)
    doc = load_document_local(sys.argv[1])
    print(f"pubmed_id           : {doc['pubmed_id']}")
    print(f"text_data length    : {len(doc['text_data'])} chars")
    print(f"structured_tables   : {len(doc['structured_tables'])} table(s)")
    print(f"first 400 chars     : {doc['text_data'][:400]}")
    if doc['structured_tables']:
        first = doc['structured_tables'][0]
        print(f"first table context : {first.get('context')}")
        print(f"first table headers : {first.get('headers')}")
        print(f"first table rows[0] : {(first.get('rows') or [[]])[0]}")
