"""Parse markdown tables from Azure DI output into explicit Row/Col format."""
import re
from typing import Optional


def parse_markdown_tables(markdown_text: str) -> list[dict]:
    """Return [{context, headers, rows}, ...] for every markdown table found."""
    if not markdown_text:
        return []

    lines = markdown_text.splitlines()
    tables: list[dict] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if line.strip().startswith("|") and "|" in line[1:]:
            if i + 1 < n and re.match(r"^\s*\|?\s*[:\- ]+\|", lines[i + 1]):
                context = _find_context(lines, i)
                headers = _split_row(lines[i])
                rows: list[list[str]] = []
                i += 2
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(_split_row(lines[i]))
                    i += 1
                tables.append({"context": context, "headers": headers, "rows": rows})
                continue
        i += 1

    return tables


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _find_context(lines: list[str], idx: int) -> str:
    for j in range(idx - 1, max(-1, idx - 6), -1):
        s = lines[j].strip()
        if not s or s.startswith("|"):
            continue
        return s[:200]
    return ""


def format_tables_for_llm(tables: list[dict]) -> str:
    """Explicit Row/Col format. Reduces LLM row-miss errors."""
    if not tables:
        return ""
    out: list[str] = []
    for t_idx, t in enumerate(tables, 1):
        ctx = t.get("context") or ""
        out.append(f"Table {t_idx}: {ctx}".rstrip())
        headers = t.get("headers") or []
        rows = t.get("rows") or []
        for r_idx, row in enumerate(rows, 1):
            cells = []
            for c_idx, val in enumerate(row):
                col = headers[c_idx] if c_idx < len(headers) else f"Col{c_idx + 1}"
                cells.append(f"{col}={val}")
            out.append(f"  Row {r_idx}: " + " | ".join(cells))
        out.append("")
    return "\n".join(out)


def format_document_tables(markdown_text: Optional[str]) -> str:
    return format_tables_for_llm(parse_markdown_tables(markdown_text or ""))
