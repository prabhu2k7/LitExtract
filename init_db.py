"""SQLite schema + lightweight migrations for db/extraction_state.db."""
import sqlite3
import json
from datetime import datetime, timezone
from typing import Any

import config

# Per-1M-token pricing in USD. ALWAYS use gpt-4o-mini pricing for gpt-4o-mini.
_MODEL_PRICING = {
    "gpt-4o-mini":      {"input": 0.15, "output": 0.60},
    "gpt-4.1-mini":     {"input": 0.40, "output": 1.60},
    "gpt-4.1":          {"input": 2.00, "output": 8.00},
    "gpt-4o":           {"input": 2.50, "output": 10.00},
    "gpt-5.4-mini":     {"input": 0.50, "output": 2.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6":   {"input": 15.00, "output": 75.00},
}


_RUNS_OPENAI_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs_openai (
    run_id TEXT PRIMARY KEY,
    pubmed_id TEXT NOT NULL,
    run_datetime TEXT,
    prompt_version TEXT,
    study_types TEXT,
    disease TEXT,
    BM_Details REAL,
    Study_Results REAL,
    BM_Results REAL,
    Inferences REAL,
    Row_Recall REAL,
    Field_Precision REAL,
    F1 REAL,
    llm_model TEXT,
    extraction_input_tokens INTEGER,
    extraction_output_tokens INTEGER,
    extraction_total_tokens INTEGER,
    extraction_cost_usd REAL,
    verification_input_tokens INTEGER,
    verification_output_tokens INTEGER,
    verification_total_tokens INTEGER,
    verification_cost_usd REAL,
    cost_usd_per_paper REAL,
    study_details_count INTEGER,
    bm_details_count INTEGER,
    bm_results_count INTEGER,
    inferences_count INTEGER,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    prompt_hash TEXT,
    gold_bm_results_count INTEGER,
    bm_types TEXT,
    confidence TEXT,
    confidence_reason TEXT
);
"""

_LLM_COMPARISON_SCHEMA = """
CREATE TABLE IF NOT EXISTS LLM_comparison (
    run_id TEXT PRIMARY KEY,
    pubmed_id TEXT NOT NULL,
    llm_name TEXT,
    f1_score REAL,
    cost_usd REAL,
    run_datetime TEXT,
    F1 REAL,
    BM_Details REAL,
    Study_Results REAL,
    BM_Results REAL,
    Inferences REAL,
    Row_Recall REAL,
    Field_Precision REAL,
    extraction_cost_usd REAL,
    notes TEXT
);
"""

_EXTRACTION_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS extraction_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pubmed_id TEXT NOT NULL,
    run_id TEXT,
    run_datetime TEXT,
    model TEXT,
    disease TEXT,
    study_types TEXT,
    bm_types TEXT,
    cost_usd REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    notes TEXT
);
"""

# UI-flow uploads table.
# Purpose-built for the FastAPI upload pipeline (one row per uploaded PDF).
# Lives alongside runs_openai (which stays focused on batch + verification).
# Linkage: uploads.run_id <-> runs_openai.run_id, uploads.display_id <-> runs_openai.pubmed_id.
_UPLOADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    -- Identity
    upload_id          TEXT PRIMARY KEY,              -- internal UUID, never user-facing
    display_id         TEXT NOT NULL,                 -- shown in UI; PMID if detected, else filename stem
    pmid               TEXT,                          -- detected PMID (nullable)
    original_filename  TEXT NOT NULL,                 -- as-uploaded filename
    pdf_path           TEXT,                          -- where the PDF lives on disk
    pdf_size_bytes     INTEGER,
    pdf_sha256         TEXT,                          -- duplicate detection

    -- Lifecycle
    state              TEXT NOT NULL DEFAULT 'queued',-- queued|processing|complete|failed
    stage              TEXT,                          -- last-known stage tag
    error_message      TEXT,
    uploaded_at        TEXT NOT NULL,
    started_at         TEXT,
    completed_at       TEXT,
    duration_ms        INTEGER,

    -- Classification (denormalised for fast list views)
    disease            TEXT,
    study_types        TEXT,                          -- JSON array
    bm_types           TEXT,                          -- JSON array
    confidence_level   TEXT,                          -- HIGH|MEDIUM|LOW

    -- Output counts
    study_details_count INTEGER,
    bm_details_count    INTEGER,
    bm_results_count    INTEGER,
    inferences_count    INTEGER,

    -- LLM / cost
    model              TEXT,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    total_tokens       INTEGER,
    cost_usd           REAL,
    prompt_hash        TEXT,

    -- Run linkage (1:1 with runs_openai for now; could grow to 1:N if reruns)
    run_id             TEXT,

    -- Soft delete (preserve audit trail)
    deleted_at         TEXT
);
"""

_UPLOADS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_uploads_state         ON uploads(state)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_uploaded_at   ON uploads(uploaded_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_pmid          ON uploads(pmid)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_display_id    ON uploads(display_id)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_pdf_sha256    ON uploads(pdf_sha256)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_run_id        ON uploads(run_id)",
]

# (table, column, type) — added via ALTER TABLE if missing
_MIGRATIONS = [
    ("runs_openai", "prompt_hash", "TEXT"),
    ("runs_openai", "gold_bm_results_count", "INTEGER"),
    ("runs_openai", "bm_types", "TEXT"),
    ("runs_openai", "confidence", "TEXT"),
    ("runs_openai", "confidence_reason", "TEXT"),
    # uploads — flags for v0.2 (training/force/cache)
    ("uploads", "training_mode", "INTEGER DEFAULT 0"),
    ("uploads", "force_rerun", "INTEGER DEFAULT 0"),
    ("uploads", "training_iterations_used", "INTEGER"),
    ("uploads", "training_iterations_max", "INTEGER"),
    ("uploads", "training_f1_initial", "REAL"),
    ("uploads", "training_f1_final", "REAL"),
    ("uploads", "training_prompt_changes", "TEXT"),
    ("uploads", "gold_source", "TEXT"),
    # cache hits get a separate row pointing at the original
    ("uploads", "skip_reason", "TEXT"),
    ("uploads", "cached_from_upload_id", "TEXT"),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and run migrations. Safe to call repeatedly."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(_RUNS_OPENAI_SCHEMA)
        conn.execute(_LLM_COMPARISON_SCHEMA)
        conn.execute(_EXTRACTION_LOG_SCHEMA)
        conn.execute(_UPLOADS_SCHEMA)
        for stmt in _UPLOADS_INDEXES:
            conn.execute(stmt)
        for table, col, coltype in _MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_extraction_log(pubmed_id: str, run_id: str, data: dict[str, Any]) -> None:
    """Insert a row into extraction_log."""
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO extraction_log
               (pubmed_id, run_id, run_datetime, model, disease, study_types,
                bm_types, cost_usd, input_tokens, output_tokens, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pubmed_id,
                run_id,
                data.get("run_datetime") or _now(),
                data.get("model"),
                data.get("disease"),
                json.dumps(data.get("study_types") or []),
                json.dumps(data.get("bm_types") or []),
                data.get("cost_usd"),
                data.get("input_tokens"),
                data.get("output_tokens"),
                data.get("notes"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_benchmark_row(
    pubmed_id: str,
    scores: dict[str, Any],
    model_name: str,
    table: str = "runs_openai",
) -> None:
    """Insert one F1-scores row into runs_openai (or LLM_comparison)."""
    run_id = scores.get("run_id") or f"{pubmed_id}_{_now().replace(' ', 'T')}"
    conn = _connect()
    try:
        if table == "runs_openai":
            conn.execute(
                """INSERT OR REPLACE INTO runs_openai
                   (run_id, pubmed_id, run_datetime, prompt_version,
                    study_types, disease, BM_Details, Study_Results,
                    BM_Results, Inferences, Row_Recall, Field_Precision, F1,
                    llm_model, extraction_input_tokens, extraction_output_tokens,
                    extraction_total_tokens, extraction_cost_usd,
                    verification_input_tokens, verification_output_tokens,
                    verification_total_tokens, verification_cost_usd,
                    cost_usd_per_paper, study_details_count, bm_details_count,
                    bm_results_count, inferences_count, status, notes,
                    prompt_hash, gold_bm_results_count, bm_types,
                    confidence, confidence_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, pubmed_id, scores.get("run_datetime") or _now(),
                    scores.get("prompt_version"),
                    json.dumps(scores.get("study_types") or []),
                    scores.get("disease"),
                    scores.get("BM_Details"), scores.get("Study_Results"),
                    scores.get("BM_Results"), scores.get("Inferences"),
                    scores.get("Row_Recall"), scores.get("Field_Precision"),
                    scores.get("F1"), model_name,
                    scores.get("extraction_input_tokens"),
                    scores.get("extraction_output_tokens"),
                    scores.get("extraction_total_tokens"),
                    scores.get("extraction_cost_usd"),
                    scores.get("verification_input_tokens"),
                    scores.get("verification_output_tokens"),
                    scores.get("verification_total_tokens"),
                    scores.get("verification_cost_usd"),
                    scores.get("cost_usd_per_paper"),
                    scores.get("study_details_count"),
                    scores.get("bm_details_count"),
                    scores.get("bm_results_count"),
                    scores.get("inferences_count"),
                    scores.get("status", "complete"),
                    scores.get("notes"),
                    scores.get("prompt_hash"),
                    scores.get("gold_bm_results_count"),
                    json.dumps(scores.get("bm_types") or []),
                    scores.get("confidence"),
                    scores.get("confidence_reason"),
                ),
            )
        else:
            conn.execute(
                """INSERT OR REPLACE INTO LLM_comparison
                   (run_id, pubmed_id, llm_name, f1_score, cost_usd, run_datetime,
                    F1, BM_Details, Study_Results, BM_Results, Inferences,
                    Row_Recall, Field_Precision, extraction_cost_usd, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, pubmed_id, model_name,
                    scores.get("F1"), scores.get("cost_usd_per_paper"),
                    scores.get("run_datetime") or _now(),
                    scores.get("F1"), scores.get("BM_Details"),
                    scores.get("Study_Results"), scores.get("BM_Results"),
                    scores.get("Inferences"), scores.get("Row_Recall"),
                    scores.get("Field_Precision"),
                    scores.get("extraction_cost_usd"),
                    scores.get("notes"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ---- uploads table helpers ----

def insert_upload(row: dict[str, Any]) -> None:
    """Insert a fresh uploads row (state=queued)."""
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO uploads
               (upload_id, display_id, pmid, original_filename, pdf_path,
                pdf_size_bytes, pdf_sha256, state, stage, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["upload_id"], row["display_id"], row.get("pmid"),
                row["original_filename"], row.get("pdf_path"),
                row.get("pdf_size_bytes"), row.get("pdf_sha256"),
                row.get("state", "queued"), row.get("stage", "queued"),
                row.get("uploaded_at") or _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_upload(upload_id: str, fields: dict[str, Any]) -> None:
    """Update arbitrary columns on an uploads row by upload_id."""
    if not fields:
        return
    cols = list(fields.keys())
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    values = [fields[c] for c in cols] + [upload_id]
    conn = _connect()
    try:
        conn.execute(f"UPDATE uploads SET {set_clause} WHERE upload_id = ?", values)
        conn.commit()
    finally:
        conn.close()


def get_upload_by_display_id(display_id: str) -> dict[str, Any] | None:
    """Return the most recent (non-deleted) upload row for a display_id."""
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT * FROM uploads
               WHERE display_id = ? AND deleted_at IS NULL
               ORDER BY uploaded_at DESC LIMIT 1""",
            (display_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_uploads(limit: int = 100) -> list[dict[str, Any]]:
    """Most recent upload per display_id, newest first."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT u.*
               FROM uploads u
               JOIN (
                   SELECT display_id, MAX(uploaded_at) AS max_at
                   FROM uploads
                   WHERE deleted_at IS NULL
                   GROUP BY display_id
               ) latest
               ON u.display_id = latest.display_id AND u.uploaded_at = latest.max_at
               WHERE u.deleted_at IS NULL
               ORDER BY u.uploaded_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {config.DB_PATH}")
