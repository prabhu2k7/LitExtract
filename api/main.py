"""FastAPI backend for the Biomarker Research UI.

Routes:
  POST /api/upload          -> upload a PDF, kicks off background extraction, returns paper_id
  GET  /api/status/{id}     -> { state: queued|processing|complete|failed, ... }
  GET  /api/results/{id}    -> full extracted payload (4 sheets) + run metadata
  GET  /api/download/{id}   -> Excel file (.xlsx) with 4 sheets
  GET  /api/history         -> list of past extractions from SQLite
  GET  /api/health          -> { ok: true, model: ... }

Runs the existing 4-agent pipeline (pipeline_local.LocalExtractionPipeline).
"""
from __future__ import annotations
import io
import os
import sys
import uuid
import json
import threading
import hashlib
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

# --- Make repo root importable so we can use existing modules unchanged ---
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd  # noqa: E402
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse, JSONResponse  # noqa: E402

import config  # noqa: E402
import init_db as _initdb  # noqa: E402
from pipeline_local import LocalExtractionPipeline, load_extracted_for_paper  # noqa: E402
from column_mappings import SHEET_COLUMNS  # noqa: E402
from pmid_detector import derive_display_id, detect_pmid_from_text  # noqa: E402
from api.security import (  # noqa: E402
    SecurityHeadersMiddleware,
    install_log_redaction,
    get_cors_origins,
    get_user_api_key,
    require_api_key,
    resolve_api_key,
    sanitize_error,
    limiter,
)


# Install log redaction as soon as possible — before any request fires.
install_log_redaction()

# Initialise the SQLite schema at startup so read-only endpoints (history,
# biomarkers) work even before the first upload triggers pipeline init.
_initdb.init_db()


# ---- App ----
app = FastAPI(title="Biomarker Research API", version="0.1.0")

# Security headers on every response (CSP, HSTS, frame-deny, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# CORS — env-driven allowlist. No wildcard in production. Defaults to Vite dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,  # we don't use cookies/sessions
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-OpenAI-Api-Key"],
    expose_headers=["Content-Disposition"],
    max_age=3600,
)

# Per-IP rate limiting (slowapi). Limits applied per-route below.
if limiter is not None:
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request, exc):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
        )


# ---- Per-request pipeline (BYOK) ----
# Each /api/upload call constructs a fresh LocalExtractionPipeline whose LLM
# client is bound to that request's resolved key (header > env). The pipeline
# instance, the LLM client, and the key all go out of scope when the request
# handler returns — Python's GC drops them. We never cache them in process
# globals when BYOK is in play.

def build_pipeline_for_request(api_key: str) -> LocalExtractionPipeline:
    """Construct a per-request pipeline bound to the resolved API key.

    The `api_key` arg is held only by the LangChain client inside the returned
    pipeline. It is never written to disk, DB, or logs by this code path.
    """
    return LocalExtractionPipeline(api_key=api_key)


# ---- In-memory job store (process-lifetime). State also lands in SQLite for history. ----
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _set_job(paper_id: str, **fields: Any) -> None:
    with _jobs_lock:
        job = _jobs.setdefault(paper_id, {})
        job.update(fields)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()


def _get_job(paper_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(paper_id)
        return dict(job) if job else None


class _CancelledByUser(Exception):
    """Raised by the stage callback when the user hit Cancel mid-extraction."""


def _run_extraction(paper_id: str, upload_id: str, pdf_path: Path,
                     api_key: str) -> None:
    """Background worker. Runs the pipeline and keeps both the in-memory job
    store and the SQLite uploads row in sync.

    `api_key` is the resolved BYOK value for this run. It lives only in the
    LLM client created here and is dropped when the function returns.
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    _set_job(paper_id, state="processing", stage="parsing_pdf")
    _initdb.update_upload(upload_id, {
        "state": "processing",
        "stage": "parsing_pdf",
        "started_at": started_at,
    })
    t0 = datetime.now(timezone.utc)

    def stage_cb(stage_name: str) -> None:
        """Invoked by the pipeline at every sub-stage transition.

        Also serves as the cancellation checkpoint — if the user hit Cancel
        while a stage was in flight, the next sub-stage transition raises
        `CancelledError`, which the outer except handles by marking the
        upload as 'cancelled' (distinct from 'failed').
        """
        if _initdb.get_upload_state(upload_id) == "cancelling":
            raise _CancelledByUser(f"cancelled at stage {stage_name}")
        _set_job(paper_id, stage=stage_name)
        _initdb.update_upload(upload_id, {"stage": stage_name})

    try:
        pipeline = build_pipeline_for_request(api_key)
        result = pipeline.process_pdf(
            pdf_path, paper_id=paper_id, stage_callback=stage_cb
        )

        # Late-stage PMID enrichment from PDF text — doesn't change display_id
        # (we don't want stable URLs to shift), only fills the pmid metadata.
        try:
            from pdf_extractor import load_document_local  # cheap re-read
            doc = load_document_local(pdf_path, pubmed_id=paper_id)
            text_pmid = detect_pmid_from_text(doc.get("text_data", ""))
        except Exception:
            text_pmid = None

        cls = result.get("classification") or {}
        cost = result.get("cost") or {}
        counts = result.get("counts") or {}
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)

        _initdb.update_upload(upload_id, {
            "state": "complete",
            "stage": "done",
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "disease": cls.get("disease"),
            "study_types": json.dumps(cls.get("study_types") or []),
            "bm_types": json.dumps(cls.get("bm_types") or []),
            "confidence_level": cls.get("confidence_level"),
            "study_details_count": counts.get("Study_Details"),
            "bm_details_count": counts.get("BM_Details"),
            "bm_results_count": counts.get("BM_Results"),
            "inferences_count": counts.get("Inferences"),
            "model": result.get("model"),
            "input_tokens": cost.get("input_tokens"),
            "output_tokens": cost.get("output_tokens"),
            "total_tokens": cost.get("total_tokens"),
            "cost_usd": cost.get("cost_usd"),
            "run_id": result.get("run_id"),
            # only enrich pmid if we found one and the row didn't already have one
            **({"pmid": text_pmid} if text_pmid else {}),
        })

        _set_job(
            paper_id,
            state="complete",
            stage="done",
            result=result,
            error=None,
        )
    except _CancelledByUser as e:
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        _initdb.update_upload(upload_id, {
            "state": "cancelled",
            "stage": "cancelled",
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "error_message": str(e),
        })
        _set_job(paper_id, state="cancelled", stage="cancelled", error=str(e))
    except Exception as e:
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        # Sanitize before persisting / surfacing to the client. OpenAI's error
        # payloads occasionally echo the request key in plaintext — scrub.
        safe_msg = sanitize_error(str(e))[:2000]
        safe_tb = sanitize_error(traceback.format_exc())
        _initdb.update_upload(upload_id, {
            "state": "failed",
            "stage": "error",
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "error_message": safe_msg,
        })
        _set_job(
            paper_id,
            state="failed",
            stage="error",
            error=safe_msg,
            traceback=safe_tb,
        )


# ---- Routes ----

_PROVIDER_LABELS = {
    "openai":       "OpenAI",
    "anthropic":    "Anthropic",
    "azure-openai": "Azure OpenAI",
}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": config.active_model_name(),
        "provider": config.LLM_PROVIDER,
        "provider_label": _PROVIDER_LABELS.get(config.LLM_PROVIDER, config.LLM_PROVIDER),
        "byok_required": resolve_api_key(None) is None,
    }


@app.post("/api/test-key")
@(limiter.limit("10/minute") if limiter else (lambda f: f))
async def test_key(
    request: Request,
    user_api_key: str | None = Depends(get_user_api_key),
) -> dict[str, Any]:
    """Validate that an API key works WITHOUT consuming meaningful tokens.

    Strategy: hit OpenAI's `/v1/models` endpoint — read-only, no completion,
    fastest signal of a working key. Returns ok=true if 200, error otherwise.

    Always returns 200 to the client (even on key failure), embedding success
    state in the body — keeps the UI logic simpler. The key itself is never
    echoed back; only a masked tail (`...7a3f`) so the user can confirm what
    they sent.
    """
    api_key = (user_api_key or "").strip() or (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "reason": "missing",
            "message": "No API key supplied.",
        }

    masked = (
        f"sk-...{api_key[-4:]}" if len(api_key) >= 4 else "sk-..."
    ) if api_key.startswith("sk-") else "(non-sk key)"

    # Use httpx directly — avoids touching LangChain (less surface area for
    # leaks). 5-second timeout — this should be near-instant.
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code == 200:
            data = r.json()
            model_ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
            target = config.OPENAI_COMPLETION_MODEL
            return {
                "ok": True,
                "key_masked": masked,
                "default_model": target,
                "model_available": target in model_ids,
                "models_count": len(model_ids),
            }
        if r.status_code in (401, 403):
            return {
                "ok": False,
                "reason": "invalid",
                "message": "OpenAI rejected the key.",
                "key_masked": masked,
            }
        return {
            "ok": False,
            "reason": "openai_error",
            "message": sanitize_error(f"OpenAI returned {r.status_code}"),
            "key_masked": masked,
        }
    except Exception as e:
        return {
            "ok": False,
            "reason": "network",
            "message": sanitize_error(str(e))[:200],
            "key_masked": masked,
        }




# Stages reference — shared with the frontend so labels and percentages stay
# consistent between server and client.
from pipeline_local import PIPELINE_STAGES  # noqa: E402

_STAGE_LABELS = {
    "queued":                    "Queued",
    "parsing_pdf":               "Reading PDF",
    "classifying":               "Classifying study",
    "extracting_study_details":  "Extracting study details",
    "extracting_bm_details":     "Extracting biomarkers",
    "extracting_bm_results":     "Extracting results",
    "extracting_inferences":     "Extracting inferences",
    "writing_excel":             "Compiling output",
    "done":                      "Complete",
    "cached":                    "Cached",
    "error":                     "Failed",
}


def _stage_progress_pct(stage: str | None) -> int:
    """Cumulative typical-percent for a given stage name."""
    if not stage:
        return 0
    cum = 0
    for name, share in PIPELINE_STAGES:
        if name == stage:
            return cum
        cum += share
    return cum


@app.get("/api/stages")
def stages_reference() -> dict[str, Any]:
    """Shared reference: ordered stage names + labels + cumulative percent."""
    cum = 0
    items = []
    for name, share in PIPELINE_STAGES:
        items.append({
            "name":       name,
            "label":      _STAGE_LABELS.get(name, name),
            "share_pct":  share,
            "cum_pct":    min(100, cum + share),
        })
        cum += share
    return {"stages": items}


@app.get("/api/eta")
def eta(window: int = 10) -> dict[str, Any]:
    """Rolling-average duration AND cost across the most recent `window`
    complete uploads. Used by the UI to render time + cost estimates.

    Returns nulls when no history; the UI then falls back to a static
    "30-90 seconds typical" copy and no cost estimate.
    """
    sql = text("""
        SELECT duration_ms, cost_usd, model FROM uploads
        WHERE state = 'complete'
          AND duration_ms IS NOT NULL
          AND duration_ms > 0
          AND skip_reason IS NULL
          AND deleted_at IS NULL
        ORDER BY uploaded_at DESC LIMIT :win
    """)
    try:
        with _initdb.get_engine().connect() as conn:
            rows = conn.execute(sql, {"win": window}).mappings().all()
    except Exception:
        rows = []
    durs = [r["duration_ms"] for r in rows if r["duration_ms"]]
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    if not durs:
        return {
            "avg_duration_ms": None,
            "avg_cost_usd": None,
            "samples": 0,
            "window": window,
            "model": config.active_model_name(),
        }
    return {
        "avg_duration_ms": int(sum(durs) / len(durs)),
        "min_duration_ms": min(durs),
        "max_duration_ms": max(durs),
        "avg_cost_usd": (sum(costs) / len(costs)) if costs else None,
        "min_cost_usd": min(costs) if costs else None,
        "max_cost_usd": max(costs) if costs else None,
        "samples": len(durs),
        "window": window,
        "model": config.active_model_name(),
    }


@app.post("/api/upload")
@(limiter.limit("10/minute") if limiter else (lambda f: f))
async def upload(
    request: Request,
    file: UploadFile = File(...),
    force_rerun: bool = Form(False),
    training_mode: bool = Form(False),
    user_api_key: str | None = Depends(get_user_api_key),
) -> dict[str, Any]:
    # Resolve key first — fail fast before reading the file body.
    api_key = require_api_key(user_api_key)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted")

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    safe_name = Path(file.filename).name
    sha = hashlib.sha256(body).hexdigest()
    upload_id = uuid.uuid4().hex
    uploaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # CACHE SHORTCUT — if the same SHA already has a complete extraction and
    # the user did NOT request force_rerun, return that previous run directly.
    # We still write a fresh uploads row for audit (skip_reason tells the story).
    if not force_rerun:
        prior = _find_complete_by_sha(sha)
        if prior is not None:
            display_id = prior["display_id"]
            _initdb.insert_upload({
                "upload_id": upload_id,
                "display_id": display_id,        # reuse — points at the same paper
                "pmid": prior.get("pmid"),
                "original_filename": safe_name,
                "pdf_path": prior.get("pdf_path"),
                "pdf_size_bytes": len(body),
                "pdf_sha256": sha,
                "state": "complete",
                "stage": "cached",
                "uploaded_at": uploaded_at,
            })
            # Carry over the cached metrics so /api/history sees them
            _initdb.update_upload(upload_id, {
                "completed_at": uploaded_at,
                "duration_ms": 0,
                "skip_reason": "cache_hit_sha256",
                "cached_from_upload_id": prior.get("upload_id"),
                "disease": prior.get("disease"),
                "study_types": prior.get("study_types"),
                "bm_types": prior.get("bm_types"),
                "confidence_level": prior.get("confidence_level"),
                "study_details_count": prior.get("study_details_count"),
                "bm_details_count": prior.get("bm_details_count"),
                "bm_results_count": prior.get("bm_results_count"),
                "inferences_count": prior.get("inferences_count"),
                "model": prior.get("model"),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0,
                "training_mode": int(bool(training_mode)),
                "force_rerun": 0,
            })
            return {
                "paper_id": display_id,
                "display_id": display_id,
                "upload_id": upload_id,
                "pmid": prior.get("pmid"),
                "filename": safe_name,
                "size_bytes": len(body),
                "state": "complete",
                "cached": True,
                "cached_from": {
                    "display_id": prior["display_id"],
                    "uploaded_at": prior.get("uploaded_at"),
                },
                "duplicate_of": None,
            }

    # Decide the user-facing display_id from the filename only (PMID-aware).
    proposed_display_id, detected_pmid = derive_display_id(safe_name)
    display_id = _ensure_unique_display_id(proposed_display_id)

    # Persist PDF as input/<display_id>__<original_name>.pdf
    dest = config.PROJECT_ROOT / "input" / f"{display_id}__{safe_name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)

    # Write uploads row (queued state). The worker fills the rest.
    _initdb.insert_upload({
        "upload_id": upload_id,
        "display_id": display_id,
        "pmid": detected_pmid,
        "original_filename": safe_name,
        "pdf_path": str(dest),
        "pdf_size_bytes": len(body),
        "pdf_sha256": sha,
        "state": "queued",
        "stage": "queued",
        "uploaded_at": uploaded_at,
    })
    # Record the user's flags on the row
    _initdb.update_upload(upload_id, {
        "training_mode": int(bool(training_mode)),
        "force_rerun":   int(bool(force_rerun)),
    })

    _set_job(
        display_id,
        upload_id=upload_id,
        state="queued",
        stage="queued",
        original_filename=safe_name,
        pdf_path=str(dest),
        size_bytes=len(body),
        pdf_sha256=sha,
        pmid=detected_pmid,
        training_mode=bool(training_mode),
        force_rerun=bool(force_rerun),
    )

    threading.Thread(
        target=_run_extraction,
        args=(display_id, upload_id, dest, api_key),
        daemon=True,
    ).start()

    return {
        "paper_id": display_id,
        "display_id": display_id,
        "upload_id": upload_id,
        "pmid": detected_pmid,
        "filename": safe_name,
        "size_bytes": len(body),
        "state": "queued",
        "cached": False,
        "training_mode": bool(training_mode),
        "force_rerun": bool(force_rerun),
        "duplicate_of": _find_duplicate(sha, exclude_upload_id=upload_id),
    }


def _find_complete_by_sha(sha: str) -> dict | None:
    """Return the most recent COMPLETE upload row matching this SHA256, or None."""
    if not sha:
        return None
    sql = text("""
        SELECT * FROM uploads
        WHERE pdf_sha256 = :sha
          AND state = 'complete'
          AND deleted_at IS NULL
        ORDER BY uploaded_at DESC LIMIT 1
    """)
    try:
        with _initdb.get_engine().connect() as conn:
            row = conn.execute(sql, {"sha": sha}).mappings().first()
    except Exception:
        return None
    return dict(row) if row else None


def _ensure_unique_display_id(proposed: str) -> str:
    """If proposed display_id already exists in uploads, suffix '-2', '-3', etc.
    Keeps URLs stable per upload — re-uploads of the same paper get a fresh id."""
    base = proposed
    candidate = base
    i = 2
    while _initdb.get_upload_by_display_id(candidate) is not None:
        candidate = f"{base}-{i}"
        i += 1
        if i > 99:
            # extremely unlikely; fall back to UUID suffix
            candidate = f"{base}-{uuid.uuid4().hex[:6]}"
            break
    return candidate


def _find_duplicate(sha: str, exclude_upload_id: str | None = None) -> dict | None:
    """Return the most recent prior upload with the same SHA256 (or None).
    Used to flag duplicate-content uploads in the response."""
    if not sha:
        return None
    sql = text("""
        SELECT upload_id, display_id, original_filename, uploaded_at
        FROM uploads
        WHERE pdf_sha256 = :sha
          AND deleted_at IS NULL
          AND upload_id != COALESCE(:exclude, '')
        ORDER BY uploaded_at DESC LIMIT 1
    """)
    try:
        with _initdb.get_engine().connect() as conn:
            row = conn.execute(
                sql, {"sha": sha, "exclude": exclude_upload_id}
            ).mappings().first()
    except Exception:
        return None
    return dict(row) if row else None


@app.get("/api/status/{paper_id}")
def status(paper_id: str) -> dict[str, Any]:
    job = _get_job(paper_id)

    # Always look up the persisted uploads row — it survives process restarts.
    upload_row = _initdb.get_upload_by_display_id(paper_id)

    if job is None and upload_row is None:
        raise HTTPException(status_code=404, detail="paper_id not found")

    # Prefer the live in-memory job state when present (mid-flight stages),
    # otherwise fall back to the DB row.
    state = (job or {}).get("state") or (upload_row or {}).get("state")
    stage = (job or {}).get("stage") or (upload_row or {}).get("stage")
    filename = (job or {}).get("original_filename") or (upload_row or {}).get("original_filename")
    upload_id = (job or {}).get("upload_id") or (upload_row or {}).get("upload_id")
    pmid = (job or {}).get("pmid") or (upload_row or {}).get("pmid")

    # Compute progress + elapsed for the UI
    started_at = (upload_row or {}).get("started_at")
    completed_at = (upload_row or {}).get("completed_at")
    elapsed_ms: int | None = None
    if started_at:
        try:
            t_start = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            t_end = (datetime.strptime(completed_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                     if completed_at else datetime.now(timezone.utc))
            elapsed_ms = max(0, int((t_end - t_start).total_seconds() * 1000))
        except Exception:
            elapsed_ms = None

    response: dict[str, Any] = {
        "paper_id": paper_id,
        "display_id": paper_id,
        "upload_id": upload_id,
        "pmid": pmid,
        "filename": filename,
        "state": state,
        "stage": stage,
        "stage_label": _STAGE_LABELS.get(stage or "", stage or ""),
        "progress_pct": _stage_progress_pct(stage),
        "elapsed_ms": elapsed_ms,
        "updated_at": (job or {}).get("updated_at"),
    }

    if state == "complete":
        if job and job.get("result"):
            result = job["result"]
            response["counts"] = result.get("counts")
            response["classification"] = result.get("classification")
            response["cost"] = result.get("cost")
        elif upload_row:
            # Hydrate from persisted row
            response["counts"] = {
                "Study_Details": upload_row.get("study_details_count") or 0,
                "BM_Details":    upload_row.get("bm_details_count") or 0,
                "BM_Results":    upload_row.get("bm_results_count") or 0,
                "Inferences":    upload_row.get("inferences_count") or 0,
            }
            response["classification"] = {
                "disease": upload_row.get("disease"),
                "study_types": _safe_json(upload_row.get("study_types")),
                "bm_types": _safe_json(upload_row.get("bm_types")),
                "confidence_level": upload_row.get("confidence_level"),
            }
            response["cost"] = {
                "input_tokens":  upload_row.get("input_tokens") or 0,
                "output_tokens": upload_row.get("output_tokens") or 0,
                "total_tokens":  upload_row.get("total_tokens") or 0,
                "cost_usd":      upload_row.get("cost_usd") or 0.0,
            }

    if state == "failed":
        response["error"] = (job or {}).get("error") or (upload_row or {}).get("error_message")

    return response


def _safe_json(s: Any) -> list:
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


@app.post("/api/upload/{paper_id}/cancel")
def cancel_upload(paper_id: str) -> dict[str, Any]:
    """Request cancellation of an in-flight extraction.

    Sets state='cancelling' on the uploads row. The background worker checks
    this state at every sub-stage transition (~once per agent call) and bails
    out by raising _CancelledByUser, which the run handler converts to
    state='cancelled'. So latency between click and actual stop is at most
    one agent call (~5-30s depending on stage).

    Already-complete or already-failed uploads are no-ops.
    """
    upload_row = _initdb.get_upload_by_display_id(paper_id)
    if upload_row is None:
        raise HTTPException(status_code=404, detail="paper_id not found")

    state = upload_row.get("state")
    upload_id = upload_row.get("upload_id")

    if state in ("complete", "failed", "cancelled"):
        return {
            "paper_id": paper_id,
            "state": state,
            "cancelled": False,
            "reason": f"already_{state}",
        }
    if state == "cancelling":
        return {"paper_id": paper_id, "state": state, "cancelled": True,
                "reason": "already_cancelling"}

    _initdb.update_upload(upload_id, {"state": "cancelling",
                                      "stage": "cancelling"})
    _set_job(paper_id, state="cancelling", stage="cancelling")
    return {"paper_id": paper_id, "state": "cancelling", "cancelled": True,
            "reason": "requested"}


@app.get("/api/results/{paper_id}")
def results(paper_id: str) -> dict[str, Any]:
    job = _get_job(paper_id)
    extracted: dict[str, list[dict]] | None = None

    if job and job.get("state") == "complete" and job.get("result"):
        extracted = job["result"].get("extracted")
    if extracted is None:
        # Fall back to the workbook (covers process restart).
        extracted = load_extracted_for_paper(paper_id)
        if not any(extracted.get(k) for k in SHEET_COLUMNS):
            raise HTTPException(status_code=404, detail="No results for this paper_id")

    db_meta = _fetch_db_meta(paper_id) or {}
    upload_row = _initdb.get_upload_by_display_id(paper_id) or {}

    return {
        "paper_id": paper_id,
        "display_id": paper_id,
        "upload_id": upload_row.get("upload_id"),
        "pmid": upload_row.get("pmid"),
        "filename": upload_row.get("original_filename"),
        "uploaded_at": upload_row.get("uploaded_at"),
        "completed_at": upload_row.get("completed_at"),
        "duration_ms": upload_row.get("duration_ms"),
        "extracted": extracted,
        "counts": {k: len(extracted.get(k) or []) for k in SHEET_COLUMNS},
        "meta": db_meta,
    }


@app.get("/api/download/{paper_id}")
def download(paper_id: str):
    job = _get_job(paper_id)
    extracted: dict[str, list[dict]] | None = None
    if job and job.get("state") == "complete" and job.get("result"):
        extracted = job["result"].get("extracted")
    if extracted is None:
        extracted = load_extracted_for_paper(paper_id)
    if not any(extracted.get(k) for k in SHEET_COLUMNS):
        raise HTTPException(status_code=404, detail="No results for this paper_id")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, columns in SHEET_COLUMNS.items():
            rows = extracted.get(sheet_name) or []
            df = pd.DataFrame(rows)
            for c in columns:
                if c not in df.columns:
                    df[c] = ""
            if rows:
                df["pubmed_id"] = str(paper_id)
            df = df[columns] if not df.empty else pd.DataFrame(columns=columns)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)

    filename = f"{paper_id}_extraction.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- Flat findings CSV ----------------------------------------------------
# One row per BM_Results record, with study + biomarker + matched-inference
# fields joined in. Aimed at analysts pivoting in Excel/Power BI/Tableau.

_FLAT_COLUMNS: list[str] = [
    # Identity
    "paper_id", "filename", "pmid",
    # Study context (denormalized — repeats per row)
    "disease", "study_type", "patient_count", "geographical_region",
    "gender_distribution", "age_range", "follow_up_duration", "treatment_regimen",
    # Biomarker context (joined from BM_Details)
    "biomarker_name", "biomarker_type", "biomarker_nature", "biomarker_name_std",
    # Result fields (from BM_Results)
    "outcome_name", "outcome_direction", "statistical_test", "value_type",
    "p_value_prefix", "p_value", "significance_call",
    "r_value", "r_ci_lower", "r_ci_upper",
    "specimen", "specimen_timepoint", "methodology_technique",
    "br_application", "evidence_statement",
    # Matched inference (joined by biomarker_name + br_application)
    "inference_evidence", "inference_outcome",
    # Provenance (from the BM_Results row)
    "source_excerpt", "source_section",
]


def _build_flat_findings(paper_id: str, extracted: dict) -> "pd.DataFrame":
    """Flatten the 4 sheets into a single one-row-per-finding DataFrame."""
    study_rows   = extracted.get("Study_Details") or []
    bmd_rows     = extracted.get("BM_Details") or []
    bmr_rows     = extracted.get("BM_Results") or []
    inf_rows     = extracted.get("Inferences") or []

    # Look up structures
    study = study_rows[0] if study_rows else {}
    bmd_by_name: dict[str, dict] = {}
    for r in bmd_rows:
        key = str(r.get("biomarker_name", "")).strip().lower()
        if key:
            bmd_by_name.setdefault(key, r)

    inf_by_pair: dict[tuple[str, str], dict] = {}
    for r in inf_rows:
        bm = str(r.get("biomarker_name", "")).strip().lower()
        app_ = str(r.get("br_application", "")).strip().lower()
        if bm:
            inf_by_pair.setdefault((bm, app_), r)

    upload_row = _initdb.get_upload_by_display_id(paper_id) or {}

    out_rows: list[dict] = []
    for r in bmr_rows:
        bm_key = str(r.get("biomarker_name", "")).strip().lower()
        app_key = str(r.get("br_application", "")).strip().lower()
        bmd = bmd_by_name.get(bm_key, {})
        inf = inf_by_pair.get((bm_key, app_key), {})

        out_rows.append({
            # identity
            "paper_id": paper_id,
            "filename": upload_row.get("original_filename"),
            "pmid":     upload_row.get("pmid"),

            # study
            "disease":              study.get("disease_name"),
            "study_type":           study.get("study_type"),
            "patient_count":        study.get("patient_count"),
            "geographical_region":  study.get("geographical_region"),
            "gender_distribution":  study.get("gender_distribution"),
            "age_range":            study.get("age_range"),
            "follow_up_duration":   study.get("follow_up_duration"),
            "treatment_regimen":    study.get("treatment_regimen"),

            # biomarker
            "biomarker_name":      r.get("biomarker_name") or bmd.get("biomarker_name"),
            "biomarker_type":      bmd.get("biomarker_type"),
            "biomarker_nature":    bmd.get("biomarker_nature"),
            "biomarker_name_std":  bmd.get("biomarker_name_std"),

            # result
            "outcome_name":            r.get("outcome_name"),
            "outcome_direction":       r.get("outcome_direction"),
            "statistical_test":        r.get("statistical_test"),
            "value_type":              r.get("value_type"),
            "p_value_prefix":          r.get("p_value_prefix"),
            "p_value":                 r.get("p_value"),
            "significance_call":       r.get("significance_call"),
            "r_value":                 r.get("r_value"),
            "r_ci_lower":              r.get("r_ci_lower"),
            "r_ci_upper":              r.get("r_ci_upper"),
            "specimen":                r.get("specimen"),
            "specimen_timepoint":      r.get("specimen_timepoint"),
            "methodology_technique":   r.get("methodology_technique"),
            "br_application":          r.get("br_application"),
            "evidence_statement":      r.get("evidence_statement"),

            # inference (matched by biomarker × application)
            "inference_evidence": inf.get("evidence_statement"),
            "inference_outcome":  inf.get("bm_outcome"),

            # provenance from the BM_Results row
            "source_excerpt": r.get("source_excerpt"),
            "source_section": r.get("source_section"),
        })

    df = pd.DataFrame(out_rows)
    # Enforce column order
    for c in _FLAT_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[_FLAT_COLUMNS] if not df.empty else pd.DataFrame(columns=_FLAT_COLUMNS)


def _resolve_extracted(paper_id: str) -> dict | None:
    """Return the extracted payload from in-memory job (if any) or disk."""
    job = _get_job(paper_id)
    extracted: dict | None = None
    if job and job.get("state") == "complete" and job.get("result"):
        extracted = job["result"].get("extracted")
    if extracted is None:
        extracted = load_extracted_for_paper(paper_id)
    if not extracted or not any(extracted.get(k) for k in SHEET_COLUMNS):
        return None
    return extracted


@app.get("/api/download/{paper_id}/findings.csv")
def download_findings_csv(paper_id: str):
    """Single flat CSV — one row per BM_Results finding."""
    extracted = _resolve_extracted(paper_id)
    if extracted is None:
        raise HTTPException(status_code=404, detail="No results for this paper_id")
    df = _build_flat_findings(paper_id, extracted)
    if df.empty:
        raise HTTPException(status_code=404, detail="No BM_Results rows to flatten")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="{paper_id}_findings.csv"'
        },
    )


@app.get("/api/download/{paper_id}/json")
def download_json(paper_id: str):
    """Full extraction as a downloadable JSON document."""
    extracted = _resolve_extracted(paper_id)
    if extracted is None:
        raise HTTPException(status_code=404, detail="No results for this paper_id")
    upload_row = _initdb.get_upload_by_display_id(paper_id) or {}
    db_meta = _fetch_db_meta(paper_id) or {}
    payload = {
        "paper_id":     paper_id,
        "display_id":   paper_id,
        "upload_id":    upload_row.get("upload_id"),
        "pmid":         upload_row.get("pmid"),
        "filename":     upload_row.get("original_filename"),
        "uploaded_at":  upload_row.get("uploaded_at"),
        "completed_at": upload_row.get("completed_at"),
        "duration_ms":  upload_row.get("duration_ms"),
        "counts": {k: len(extracted.get(k) or []) for k in SHEET_COLUMNS},
        "meta": db_meta,
        "extracted": extracted,
    }
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(body),
        media_type="application/json",
        headers={
            "Content-Disposition":
                f'attachment; filename="{paper_id}_extraction.json"'
        },
    )


# ---- Biomarker-centric corpus aggregation ---------------------------------
# Aggregates across ALL papers in biomarker-cl-out.xlsx by canonical biomarker
# name. Designed to power the "Biomarkers" page (cross-paper landscape view).

def _canon(s: Any) -> str:
    """Canonicalize biomarker name for grouping (uppercase, trimmed)."""
    return str(s or "").strip().upper()


def _mode_or_first(values: list[Any]) -> str | None:
    """Return the most common non-empty value, ties broken by first-seen.

    Coerces non-strings (NaN floats from openpyxl empty cells, ints, etc.)
    to strings before strip — pandas' .astype(str) doesn't always run on
    rows that came from concat'd DataFrames where one side had NaN.
    """
    seen: dict[str, int] = {}
    order: list[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if not s or s.lower() == "nan":
            continue
        if s not in seen:
            order.append(s)
        seen[s] = seen.get(s, 0) + 1
    if not seen:
        return None
    return sorted(order, key=lambda x: (-seen[x], order.index(x)))[0]


@app.get("/api/biomarkers")
def biomarkers(limit: int = 200) -> dict[str, Any]:
    """Aggregated biomarker registry across all uploads.

    Strategy: read the canonical workbook once, group BM_Details by upper-case
    biomarker_name, attach result counts + diseases + outcomes from BM_Results
    and Inferences. Joined to uploads-table metadata for paper context.
    """
    # Read both the live, container-local cache (biomarker-cl-out.xlsx) AND
    # the repo-bundled validation snapshot. Concat + dedupe by pubmed_id so:
    #   - On HF (no live cache yet): bundled showcase is visible
    #   - On local dev (live cache populated): same data, no duplication
    #   - User uploads via HF: appear in live, layered on top of bundled
    # Bundled snapshot path is repo-relative (always next to api/main.py),
    # NOT VALIDATION_DIR, which is goldset-side and may point elsewhere.

    def _read_sheets_safe(p: Path) -> dict[str, pd.DataFrame]:
        if not p.exists():
            return {}
        try:
            return pd.read_excel(p, sheet_name=None)
        except Exception:
            return {}

    _bundled_extractions_path = (
        Path(__file__).resolve().parent.parent / "validation_set" / "extractions.xlsx"
    )
    live_sheets    = _read_sheets_safe(config.OUTPUT_FILE)
    bundled_sheets = _read_sheets_safe(_bundled_extractions_path)

    if not live_sheets and not bundled_sheets:
        return {"items": [], "count": 0, "papers_scanned": 0}

    def _merge(name: str) -> pd.DataFrame:
        a = live_sheets.get(name, pd.DataFrame())
        b = bundled_sheets.get(name, pd.DataFrame())
        if a.empty and b.empty:
            return pd.DataFrame()
        if a.empty:
            return b.copy()
        if b.empty:
            return a.copy()
        # Concat then drop duplicate (pubmed_id, all-other-cols) rows
        combined = pd.concat([a, b], ignore_index=True, sort=False)
        return combined.drop_duplicates().reset_index(drop=True)

    bmd = _merge("BM_Details")
    bmr = _merge("BM_Results")
    sd  = _merge("Study_Details")
    inf = _merge("Inferences")

    # Restrict to uploads that exist in the uploads table (active ones)
    active_pids = set()
    upload_meta: dict[str, dict] = {}
    for u in _initdb.list_uploads(limit=10_000):
        pid = str(u.get("display_id") or "")
        if pid:
            active_pids.add(pid)
            upload_meta[pid] = u

    # Showcase / validation PMIDs are also "active" — they were extracted via
    # CLI tooling, not uploaded through the UI, so they wouldn't appear in
    # the uploads table. Without this, the registry is empty on a fresh HF
    # deploy until someone uploads something.
    if bundled_sheets:
        sd_b = bundled_sheets.get("Study_Details", pd.DataFrame())
        if not sd_b.empty and "pubmed_id" in sd_b.columns:
            active_pids.update(sd_b["pubmed_id"].astype(str).tolist())

    if not active_pids:
        return {"items": [], "count": 0, "papers_scanned": 0}

    def _restrict(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return df[df["pubmed_id"].astype(str).isin(active_pids)]

    bmd = _restrict(bmd)
    bmr = _restrict(bmr)
    sd  = _restrict(sd)
    inf = _restrict(inf)

    # disease per paper (from Study_Details)
    paper_disease: dict[str, str] = {}
    if not sd.empty:
        for _, r in sd.iterrows():
            pid = str(r.get("pubmed_id"))
            d = str(r.get("disease_name") or "").strip()
            if pid and d:
                paper_disease.setdefault(pid, d)

    # Group BM_Details by canonical name; require at least one BM_Results row
    if bmd.empty:
        return {"items": [], "count": 0, "papers_scanned": len(active_pids)}

    bmd = bmd.copy()
    bmd["_canon"] = bmd["biomarker_name"].astype(str).map(_canon)
    if not bmr.empty:
        bmr = bmr.copy()
        bmr["_canon"] = bmr["biomarker_name"].astype(str).map(_canon)
    if not inf.empty:
        inf = inf.copy()
        inf["_canon"] = inf["biomarker_name"].astype(str).map(_canon)

    items: list[dict[str, Any]] = []
    for canon, group in bmd.groupby("_canon"):
        if not canon:
            continue

        paper_ids = sorted({str(p) for p in group["pubmed_id"].astype(str).tolist()
                            if p in active_pids})
        if not paper_ids:
            continue

        std = _mode_or_first(group["biomarker_name_std"].astype(str).tolist()) if "biomarker_name_std" in group.columns else None
        bm_type = _mode_or_first(group["biomarker_type"].astype(str).tolist()) if "biomarker_type" in group.columns else None
        bm_nat  = _mode_or_first(group["biomarker_nature"].astype(str).tolist()) if "biomarker_nature" in group.columns else None
        display_name = _mode_or_first(group["biomarker_name"].astype(str).tolist()) or canon

        # Results scoped to this canonical biomarker
        result_rows: list[dict] = []
        sig_count = 0
        outcomes: set[str] = set()
        applications: set[str] = set()
        if not bmr.empty:
            sub = bmr[bmr["_canon"] == canon]
            for _, r in sub.iterrows():
                outcomes.add(str(r.get("outcome_name") or "").strip())
                applications.add(str(r.get("br_application") or "").strip())
                if str(r.get("significance_call") or "").strip().lower() == "significant":
                    sig_count += 1
                row = {k: r.get(k) for k in (
                    "pubmed_id", "outcome_name", "statistical_test",
                    "value_type", "r_value", "r_ci_lower", "r_ci_upper",
                    "p_value_prefix", "p_value", "significance_call",
                    "br_application", "specimen", "methodology_technique",
                )}
                # Coerce pubmed_id to str — pandas can infer numeric for
                # all-digit PMIDs after concat. Frontend uses it as a Map
                # key + .localeCompare, both of which crash on numbers.
                if row.get("pubmed_id") is not None:
                    row["pubmed_id"] = str(row["pubmed_id"])
                result_rows.append(row)

        # Inferences scoped
        inference_rows: list[dict] = []
        if not inf.empty:
            isub = inf[inf["_canon"] == canon]
            for _, r in isub.iterrows():
                irow = {k: r.get(k) for k in (
                    "pubmed_id", "br_application", "evidence_statement",
                    "bm_outcome", "source_excerpt", "source_section",
                )}
                if irow.get("pubmed_id") is not None:
                    irow["pubmed_id"] = str(irow["pubmed_id"])
                inference_rows.append(irow)

        diseases = sorted({(paper_disease.get(p) or "").strip() for p in paper_ids
                           if paper_disease.get(p)})

        # Showcase / bundled PMIDs may not exist in upload_meta — guard min/max
        # against empty iterables (uploaded_at is purely informational here).
        ts = [upload_meta[p].get("uploaded_at") or ""
              for p in paper_ids if p in upload_meta]
        first_seen = min(ts) if ts else None
        last_seen  = max(ts) if ts else None

        items.append({
            "canonical_name":       canon,
            "display_name":         display_name,
            "biomarker_name_std":   std,
            "biomarker_type":       bm_type,
            "biomarker_nature":     bm_nat,
            "paper_ids":            paper_ids,
            "paper_count":          len(paper_ids),
            "diseases":             diseases,
            "outcomes":             sorted([o for o in outcomes if o]),
            "applications":         sorted([a for a in applications if a]),
            "result_rows":          len(result_rows),
            "significant_results":  sig_count,
            "significance_rate_pct": (
                int(round(sig_count / len(result_rows) * 100))
                if result_rows else None
            ),
            "first_seen":           first_seen,
            "last_seen":            last_seen,
            # Drilldown payload — small enough to ship inline
            "results":              result_rows,
            "inferences":           inference_rows,
        })

    # Sort: most papers first, then alphabetical canonical name
    items.sort(key=lambda x: (-x["paper_count"], x["canonical_name"]))
    items = items[:limit]
    return {"items": items, "count": len(items), "papers_scanned": len(active_pids)}


@app.get("/api/history")
def history(limit: int = 100) -> dict[str, Any]:
    """List most recent uploads (one per display_id), newest first."""
    rows = _initdb.list_uploads(limit=limit)
    items = []
    for r in rows:
        items.append({
            "display_id":          r.get("display_id"),
            "upload_id":           r.get("upload_id"),
            "pmid":                r.get("pmid"),
            "filename":            r.get("original_filename"),
            "state":               r.get("state"),
            "uploaded_at":         r.get("uploaded_at"),
            "completed_at":        r.get("completed_at"),
            "duration_ms":         r.get("duration_ms"),
            "disease":             r.get("disease"),
            "study_types":         _safe_json(r.get("study_types")),
            "bm_types":            _safe_json(r.get("bm_types")),
            "confidence":          r.get("confidence_level"),
            "model":               r.get("model"),
            "study_details_count": r.get("study_details_count"),
            "bm_details_count":    r.get("bm_details_count"),
            "bm_results_count":    r.get("bm_results_count"),
            "inferences_count":    r.get("inferences_count"),
            "extraction_cost_usd": r.get("cost_usd"),
            "error_message":       r.get("error_message"),
        })
    return {"items": items, "count": len(items)}


# ---- Validation / benchmark endpoints (public read-only) ----
# Backed by api/validation.py — reads CIViC gold + cached extractions and
# returns audit-ready JSON for the /validation page. No auth needed.

@app.get("/api/validation/summary")
def validation_summary() -> dict[str, Any]:
    from api.validation import get_summary
    return get_summary()


@app.get("/api/validation/history")
def validation_history() -> dict[str, Any]:
    from api.validation import get_history
    return get_history()


@app.get("/api/validation/paper/{pmid}")
def validation_paper_detail(pmid: str) -> dict[str, Any]:
    from api.validation import get_paper_detail
    out = get_paper_detail(pmid)
    if out.get("error"):
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@app.get("/api/validation/paper/{pmid}/download")
def validation_paper_download(pmid: str):
    """Auditable Excel pack for one paper (Summary + Canonical + Gold + Extracted)."""
    from api.validation import build_paper_xlsx
    blob = build_paper_xlsx(pmid)
    if blob is None:
        raise HTTPException(status_code=404, detail="pmid_not_in_manifest")
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                f'attachment; filename="validation_{pmid}.xlsx"'
        },
    )


@app.get("/api/validation/download")
def validation_summary_download():
    """All-papers benchmark export (Aggregate + Per_Paper + Version_History)."""
    from api.validation import build_summary_xlsx
    blob = build_summary_xlsx()
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                'attachment; filename="litextract_validation_pack.xlsx"'
        },
    )


# ---- DB helpers (read-only — writes happen inside pipeline_local) ----
# All read endpoints route through SQLAlchemy via init_db.get_engine() so the
# same code runs against SQLite (local dev) and Postgres (production).

def _exists_in_db(paper_id: str) -> bool:
    sql = text("SELECT 1 FROM runs_openai WHERE pubmed_id = :pmid LIMIT 1")
    try:
        with _initdb.get_engine().connect() as conn:
            return conn.execute(sql, {"pmid": paper_id}).first() is not None
    except Exception:
        return False


def _fetch_db_meta(paper_id: str) -> dict[str, Any] | None:
    sql = text("""
        SELECT run_id, run_datetime, llm_model, disease, study_types, bm_types,
               confidence, study_details_count, bm_details_count, bm_results_count,
               inferences_count, extraction_cost_usd, extraction_input_tokens,
               extraction_output_tokens
        FROM runs_openai
        WHERE pubmed_id = :pmid
        ORDER BY run_datetime DESC LIMIT 1
    """)
    try:
        with _initdb.get_engine().connect() as conn:
            row = conn.execute(sql, {"pmid": paper_id}).mappings().first()
    except Exception:
        return None
    if not row:
        return None
    out = dict(row)
    for k in ("study_types", "bm_types"):
        try:
            out[k] = json.loads(out.get(k) or "[]")
        except Exception:
            out[k] = []
    return out


def _fetch_history(limit: int = 100) -> list[dict[str, Any]]:
    # Kept for backwards-compat; new history endpoint reads `uploads` table
    # directly via _initdb.list_uploads().
    sql = text("""
        SELECT pubmed_id, run_datetime, llm_model, disease, study_types, bm_types,
               confidence, study_details_count, bm_details_count, bm_results_count,
               inferences_count, extraction_cost_usd
        FROM runs_openai
        WHERE pubmed_id != 'Avg'
          AND (pubmed_id, run_datetime) IN (
                SELECT pubmed_id, MAX(run_datetime)
                FROM runs_openai
                WHERE pubmed_id != 'Avg'
                GROUP BY pubmed_id
          )
        ORDER BY run_datetime DESC
        LIMIT :lim
    """)
    try:
        with _initdb.get_engine().connect() as conn:
            rows = conn.execute(sql, {"lim": limit}).mappings().all()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("study_types", "bm_types"):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except Exception:
                d[k] = []
        out.append(d)
    return out


# ---- Frontend serving (production) ----
# In production builds (HF Spaces, Render, docker-compose), the React app is
# pre-built into ./frontend/dist by the Dockerfile. We mount it here so the
# whole app — UI + API — runs on a single port, single origin.
#
# In local dev, ./frontend/dist doesn't exist. We fall back to a JSON index
# response so `npm run dev` (Vite on :5173 with /api proxy) still works.

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_INDEX_HTML = _FRONTEND_DIST / "index.html"


if _INDEX_HTML.exists():
    # Mount Vite's hashed assets directly so they're served with proper
    # cache headers and Content-Type. Anything under /assets/* is hashed,
    # so we can let the browser cache aggressively.
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIST / "assets"),
        name="assets",
    )

    # SPA fallback: any non-/api GET that doesn't hit a real file returns
    # index.html so React Router can handle the path client-side.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Don't intercept API routes — let them 404 naturally if not matched.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        # If a real file exists at that path (favicon.ico, robots.txt, etc.)
        # serve it directly.
        candidate = (_FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(_FRONTEND_DIST)  # path-traversal guard
        except ValueError:
            return FileResponse(_INDEX_HTML)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_INDEX_HTML)
else:
    # Dev fallback — Vite dev server is the front door in this case.
    @app.get("/")
    def index() -> JSONResponse:
        return JSONResponse({
            "name": "Biomarker Research API (dev mode)",
            "version": "0.1.0",
            "note": "frontend/dist not built; run `npm run dev` in /frontend or use Docker build for production",
            "docs": "/docs",
        })
