"""Read/write biomarker-cl-out.xlsx and goldset_1k.xlsx."""
from __future__ import annotations
from pathlib import Path

import pandas as pd

import config
from column_mappings import SHEET_COLUMNS, GOLDSET_FIELD_ALIASES


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


def _read_all_sheets(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        return {name: _empty_frame(cols) for name, cols in SHEET_COLUMNS.items()}
    try:
        loaded = pd.read_excel(path, sheet_name=None)
    except Exception:
        return {name: _empty_frame(cols) for name, cols in SHEET_COLUMNS.items()}
    out: dict[str, pd.DataFrame] = {}
    for name, cols in SHEET_COLUMNS.items():
        df = loaded.get(name)
        if df is None:
            out[name] = _empty_frame(cols)
        else:
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            out[name] = df[cols]
    return out


def upsert_paper(pubmed_id: str, data: dict[str, list[dict]]) -> None:
    """Remove prior rows for this pubmed_id from every sheet, then append new rows."""
    path = config.OUTPUT_FILE
    sheets = _read_all_sheets(path)

    for sheet_name, columns in SHEET_COLUMNS.items():
        df = sheets[sheet_name]
        df = df[df["pubmed_id"].astype(str) != str(pubmed_id)]
        new_rows = data.get(sheet_name) or []
        if new_rows:
            new_df = pd.DataFrame(new_rows)
            for c in columns:
                if c not in new_df.columns:
                    new_df[c] = ""
            new_df["pubmed_id"] = str(pubmed_id)
            new_df = new_df[columns]
            df = pd.concat([df, new_df], ignore_index=True)
        sheets[sheet_name] = df

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, columns in SHEET_COLUMNS.items():
            sheets[sheet_name][columns].to_excel(writer, sheet_name=sheet_name, index=False)


def load_paper_from_output(pubmed_id: str) -> dict[str, list[dict]]:
    path = config.OUTPUT_FILE
    sheets = _read_all_sheets(path)
    result: dict[str, list[dict]] = {}
    for name, df in sheets.items():
        sub = df[df["pubmed_id"].astype(str) == str(pubmed_id)]
        result[name] = sub.fillna("").to_dict(orient="records")
    return result


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower().replace("_", " ")
        mapped = GOLDSET_FIELD_ALIASES.get(key)
        if mapped:
            rename[col] = mapped
    if rename:
        df = df.rename(columns=rename)
    return df


def load_gold_standard(file_path: str | None = None) -> dict[str, pd.DataFrame]:
    path = Path(file_path) if file_path else config.GOLD_STANDARD_FILE
    if not path.exists():
        return {}
    loaded = pd.read_excel(path, sheet_name=None)
    out: dict[str, pd.DataFrame] = {}
    canonical = {n.lower(): n for n in SHEET_COLUMNS.keys()}
    for raw_name, df in loaded.items():
        key = raw_name.strip().lower().replace(" ", "_")
        target = canonical.get(key) or canonical.get(raw_name.lower())
        if target is None:
            for k, v in canonical.items():
                if k in key or key in k:
                    target = v
                    break
        if target is None:
            continue
        out[target] = _normalize_columns(df)
    return out


def load_gold_for_paper(pubmed_id: str) -> dict[str, list[dict]]:
    gold = load_gold_standard()
    out: dict[str, list[dict]] = {}
    for name, df in gold.items():
        if "pubmed_id" not in df.columns:
            out[name] = []
            continue
        sub = df[df["pubmed_id"].astype(str) == str(pubmed_id)]
        out[name] = sub.fillna("").to_dict(orient="records")
    return out
