"""Dual-driver schema + data access (SQLite local, Postgres production).

This module is the single point where SQL meets the application. It uses
SQLAlchemy Core text() queries with named parameters so the same query
strings run on both engines. UPSERT semantics are dialect-branched.

Engine selection: `config.database_url()` returns either
  - sqlite:///<path>      (default, local dev)
  - postgresql+psycopg2://...  (when DATABASE_URL is set)

All column names are lowercase so unquoted identifiers behave identically
across SQLite (case-insensitive) and Postgres (lowercases unquoted IDs).
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine

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


# ---- Engine (lazy, single shared instance) -----------------------------

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = config.database_url()
        connect_args: dict[str, Any] = {}
        if not config.is_postgres():
            # SQLite: allow cross-thread access (uvicorn workers, tests, etc.)
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            url, future=True, pool_pre_ping=True, connect_args=connect_args
        )
    return _engine


def _is_pg() -> bool:
    return config.is_postgres()


# ---- Schemas (portable across SQLite + Postgres) -----------------------
# All column names are lowercase. REAL works in both engines (Postgres
# accepts it as float4). PRIMARY KEY on TEXT works for both.

_RUNS_OPENAI_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs_openai (
    run_id TEXT PRIMARY KEY,
    pubmed_id TEXT NOT NULL,
    run_datetime TEXT,
    prompt_version TEXT,
    study_types TEXT,
    disease TEXT,
    bm_details REAL,
    study_results REAL,
    bm_results REAL,
    inferences REAL,
    row_recall REAL,
    field_precision REAL,
    f1 REAL,
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
)
"""

_LLM_COMPARISON_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_comparison (
    run_id TEXT PRIMARY KEY,
    pubmed_id TEXT NOT NULL,
    llm_name TEXT,
    f1_score REAL,
    cost_usd REAL,
    run_datetime TEXT,
    f1 REAL,
    bm_details REAL,
    study_results REAL,
    bm_results REAL,
    inferences REAL,
    row_recall REAL,
    field_precision REAL,
    extraction_cost_usd REAL,
    notes TEXT
)
"""


def _extraction_log_schema() -> str:
    """Auto-incrementing log_id is the one place dialects diverge."""
    if _is_pg():
        pk = "log_id BIGSERIAL PRIMARY KEY"
    else:
        pk = "log_id INTEGER PRIMARY KEY AUTOINCREMENT"
    return f"""
    CREATE TABLE IF NOT EXISTS extraction_log (
        {pk},
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
    )
    """


_UPLOADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    upload_id          TEXT PRIMARY KEY,
    display_id         TEXT NOT NULL,
    pmid               TEXT,
    original_filename  TEXT NOT NULL,
    pdf_path           TEXT,
    pdf_size_bytes     INTEGER,
    pdf_sha256         TEXT,
    state              TEXT NOT NULL DEFAULT 'queued',
    stage              TEXT,
    error_message      TEXT,
    uploaded_at        TEXT NOT NULL,
    started_at         TEXT,
    completed_at       TEXT,
    duration_ms        INTEGER,
    disease            TEXT,
    study_types        TEXT,
    bm_types           TEXT,
    confidence_level   TEXT,
    study_details_count INTEGER,
    bm_details_count    INTEGER,
    bm_results_count    INTEGER,
    inferences_count    INTEGER,
    model              TEXT,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    total_tokens       INTEGER,
    cost_usd           REAL,
    prompt_hash        TEXT,
    run_id             TEXT,
    deleted_at         TEXT
)
"""

_UPLOADS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_uploads_state         ON uploads(state)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_uploaded_at   ON uploads(uploaded_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_pmid          ON uploads(pmid)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_display_id    ON uploads(display_id)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_pdf_sha256    ON uploads(pdf_sha256)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_run_id        ON uploads(run_id)",
]

# ALTER TABLE migrations — added if column missing
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("runs_openai", "prompt_hash",            "TEXT"),
    ("runs_openai", "gold_bm_results_count",  "INTEGER"),
    ("runs_openai", "bm_types",               "TEXT"),
    ("runs_openai", "confidence",             "TEXT"),
    ("runs_openai", "confidence_reason",      "TEXT"),
    ("uploads", "training_mode",              "INTEGER DEFAULT 0"),
    ("uploads", "force_rerun",                "INTEGER DEFAULT 0"),
    ("uploads", "training_iterations_used",   "INTEGER"),
    ("uploads", "training_iterations_max",    "INTEGER"),
    ("uploads", "training_f1_initial",        "REAL"),
    ("uploads", "training_f1_final",          "REAL"),
    ("uploads", "training_prompt_changes",    "TEXT"),
    ("uploads", "gold_source",                "TEXT"),
    ("uploads", "skip_reason",                "TEXT"),
    ("uploads", "cached_from_upload_id",      "TEXT"),
]


# ---- Public API ----------------------------------------------------------

def init_db() -> None:
    """Create tables, indexes, and run additive ALTER-TABLE migrations.
    Idempotent — safe to call repeatedly across both engines."""
    if not config.is_postgres():
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(_RUNS_OPENAI_SCHEMA))
        conn.execute(text(_LLM_COMPARISON_SCHEMA))
        conn.execute(text(_extraction_log_schema()))
        conn.execute(text(_UPLOADS_SCHEMA))
        for stmt in _UPLOADS_INDEXES:
            conn.execute(text(stmt))

        # ALTER TABLE ADD COLUMN — check existence via SQLAlchemy inspector
        # (works on both dialects without dialect-specific PRAGMA / pg_catalog).
        insp = inspect(conn)
        for table, col, coltype in _MIGRATIONS:
            try:
                cols = {c["name"].lower() for c in insp.get_columns(table)}
            except Exception:
                cols = set()
            if col.lower() not in cols:
                # Postgres 9.6+ supports IF NOT EXISTS; SQLite doesn't.
                # We've already filtered, so plain ADD COLUMN is fine on both.
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---- extraction_log ----

def upsert_extraction_log(pubmed_id: str, run_id: str, data: dict[str, Any]) -> None:
    sql = text("""
        INSERT INTO extraction_log
            (pubmed_id, run_id, run_datetime, model, disease, study_types,
             bm_types, cost_usd, input_tokens, output_tokens, notes)
        VALUES
            (:pubmed_id, :run_id, :run_datetime, :model, :disease, :study_types,
             :bm_types, :cost_usd, :input_tokens, :output_tokens, :notes)
    """)
    params = {
        "pubmed_id":     pubmed_id,
        "run_id":        run_id,
        "run_datetime":  data.get("run_datetime") or _now(),
        "model":         data.get("model"),
        "disease":       data.get("disease"),
        "study_types":   json.dumps(data.get("study_types") or []),
        "bm_types":      json.dumps(data.get("bm_types") or []),
        "cost_usd":      data.get("cost_usd"),
        "input_tokens":  data.get("input_tokens"),
        "output_tokens": data.get("output_tokens"),
        "notes":         data.get("notes"),
    }
    with get_engine().begin() as conn:
        conn.execute(sql, params)


# ---- runs_openai / llm_comparison ----

_RUNS_OPENAI_COLS = (
    "run_id", "pubmed_id", "run_datetime", "prompt_version",
    "study_types", "disease",
    "bm_details", "study_results", "bm_results", "inferences",
    "row_recall", "field_precision", "f1",
    "llm_model",
    "extraction_input_tokens", "extraction_output_tokens",
    "extraction_total_tokens", "extraction_cost_usd",
    "verification_input_tokens", "verification_output_tokens",
    "verification_total_tokens", "verification_cost_usd",
    "cost_usd_per_paper",
    "study_details_count", "bm_details_count",
    "bm_results_count", "inferences_count",
    "status", "notes", "prompt_hash", "gold_bm_results_count",
    "bm_types", "confidence", "confidence_reason",
)

_LLM_COMPARISON_COLS = (
    "run_id", "pubmed_id", "llm_name", "f1_score", "cost_usd", "run_datetime",
    "f1", "bm_details", "study_results", "bm_results", "inferences",
    "row_recall", "field_precision", "extraction_cost_usd", "notes",
)


def _upsert_sql(table: str, cols: tuple[str, ...], conflict_col: str = "run_id") -> str:
    """Dialect-aware UPSERT helper.
    SQLite uses INSERT OR REPLACE; Postgres uses ON CONFLICT DO UPDATE.
    """
    placeholders = ", ".join(f":{c}" for c in cols)
    cols_csv = ", ".join(cols)
    if _is_pg():
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != conflict_col)
        return (
            f"INSERT INTO {table} ({cols_csv}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_col}) DO UPDATE SET {updates}"
        )
    return f"INSERT OR REPLACE INTO {table} ({cols_csv}) VALUES ({placeholders})"


def insert_benchmark_row(
    pubmed_id: str,
    scores: dict[str, Any],
    model_name: str,
    table: str = "runs_openai",
) -> None:
    """Upsert one F1-scores row into runs_openai (or llm_comparison)."""
    run_id = scores.get("run_id") or f"{pubmed_id}_{_now().replace(' ', 'T')}"
    if table == "runs_openai":
        params = {
            "run_id":            run_id,
            "pubmed_id":         pubmed_id,
            "run_datetime":      scores.get("run_datetime") or _now(),
            "prompt_version":    scores.get("prompt_version"),
            "study_types":       json.dumps(scores.get("study_types") or []),
            "disease":           scores.get("disease"),
            # The Python-side `scores` dict still uses the legacy CapsCase keys
            # (BM_Details / Study_Results / etc.); map to lowercase columns here.
            "bm_details":        scores.get("BM_Details"),
            "study_results":     scores.get("Study_Results"),
            "bm_results":        scores.get("BM_Results"),
            "inferences":        scores.get("Inferences"),
            "row_recall":        scores.get("Row_Recall"),
            "field_precision":   scores.get("Field_Precision"),
            "f1":                scores.get("F1"),
            "llm_model":         model_name,
            "extraction_input_tokens":   scores.get("extraction_input_tokens"),
            "extraction_output_tokens":  scores.get("extraction_output_tokens"),
            "extraction_total_tokens":   scores.get("extraction_total_tokens"),
            "extraction_cost_usd":       scores.get("extraction_cost_usd"),
            "verification_input_tokens":  scores.get("verification_input_tokens"),
            "verification_output_tokens": scores.get("verification_output_tokens"),
            "verification_total_tokens":  scores.get("verification_total_tokens"),
            "verification_cost_usd":      scores.get("verification_cost_usd"),
            "cost_usd_per_paper":         scores.get("cost_usd_per_paper"),
            "study_details_count":   scores.get("study_details_count"),
            "bm_details_count":      scores.get("bm_details_count"),
            "bm_results_count":      scores.get("bm_results_count"),
            "inferences_count":      scores.get("inferences_count"),
            "status":                scores.get("status", "complete"),
            "notes":                 scores.get("notes"),
            "prompt_hash":           scores.get("prompt_hash"),
            "gold_bm_results_count": scores.get("gold_bm_results_count"),
            "bm_types":              json.dumps(scores.get("bm_types") or []),
            "confidence":            scores.get("confidence"),
            "confidence_reason":     scores.get("confidence_reason"),
        }
        sql = text(_upsert_sql("runs_openai", _RUNS_OPENAI_COLS))
    else:
        params = {
            "run_id":         run_id,
            "pubmed_id":      pubmed_id,
            "llm_name":       model_name,
            "f1_score":       scores.get("F1"),
            "cost_usd":       scores.get("cost_usd_per_paper"),
            "run_datetime":   scores.get("run_datetime") or _now(),
            "f1":             scores.get("F1"),
            "bm_details":     scores.get("BM_Details"),
            "study_results":  scores.get("Study_Results"),
            "bm_results":     scores.get("BM_Results"),
            "inferences":     scores.get("Inferences"),
            "row_recall":     scores.get("Row_Recall"),
            "field_precision": scores.get("Field_Precision"),
            "extraction_cost_usd": scores.get("extraction_cost_usd"),
            "notes":          scores.get("notes"),
        }
        sql = text(_upsert_sql("llm_comparison", _LLM_COMPARISON_COLS))
    with get_engine().begin() as conn:
        conn.execute(sql, params)


# ---- uploads table helpers -----------------------------------------------

def insert_upload(row: dict[str, Any]) -> None:
    sql = text("""
        INSERT INTO uploads
            (upload_id, display_id, pmid, original_filename, pdf_path,
             pdf_size_bytes, pdf_sha256, state, stage, uploaded_at)
        VALUES
            (:upload_id, :display_id, :pmid, :original_filename, :pdf_path,
             :pdf_size_bytes, :pdf_sha256, :state, :stage, :uploaded_at)
    """)
    params = {
        "upload_id":         row["upload_id"],
        "display_id":        row["display_id"],
        "pmid":              row.get("pmid"),
        "original_filename": row["original_filename"],
        "pdf_path":          row.get("pdf_path"),
        "pdf_size_bytes":    row.get("pdf_size_bytes"),
        "pdf_sha256":        row.get("pdf_sha256"),
        "state":             row.get("state", "queued"),
        "stage":             row.get("stage", "queued"),
        "uploaded_at":       row.get("uploaded_at") or _now(),
    }
    with get_engine().begin() as conn:
        conn.execute(sql, params)


def update_upload(upload_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    cols = list(fields.keys())
    set_clause = ", ".join(f"{c} = :{c}" for c in cols)
    sql = text(f"UPDATE uploads SET {set_clause} WHERE upload_id = :upload_id")
    params = {**fields, "upload_id": upload_id}
    with get_engine().begin() as conn:
        conn.execute(sql, params)


def get_upload_by_display_id(display_id: str) -> dict[str, Any] | None:
    sql = text("""
        SELECT * FROM uploads
        WHERE display_id = :display_id AND deleted_at IS NULL
        ORDER BY uploaded_at DESC LIMIT 1
    """)
    with get_engine().connect() as conn:
        result = conn.execute(sql, {"display_id": display_id}).mappings().first()
    return dict(result) if result else None


def get_upload_state(upload_id: str) -> str | None:
    """Cheap state-only read used by the cancellation poll between stages."""
    sql = text("SELECT state FROM uploads WHERE upload_id = :upload_id")
    with get_engine().connect() as conn:
        row = conn.execute(sql, {"upload_id": upload_id}).first()
    return row[0] if row else None


def list_uploads(limit: int = 100) -> list[dict[str, Any]]:
    """Most-recent upload per display_id, newest first."""
    # Same shape works on both engines — uses a derived table with MAX().
    sql = text("""
        SELECT u.*
        FROM uploads u
        JOIN (
            SELECT display_id, MAX(uploaded_at) AS max_at
            FROM uploads
            WHERE deleted_at IS NULL
            GROUP BY display_id
        ) latest
          ON u.display_id = latest.display_id
         AND u.uploaded_at = latest.max_at
        WHERE u.deleted_at IS NULL
        ORDER BY u.uploaded_at DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    url = config.database_url()
    print(f"DB initialised at {url}")
