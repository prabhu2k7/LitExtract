"""Security primitives for the LitExtract API.

This module is the single source of truth for:
  - BYOK header handling (`X-OpenAI-Api-Key`)
  - Security response headers (CSP, HSTS, frame-deny, etc.)
  - Header redaction in logs
  - Error-message sanitization (strip `sk-` patterns before responding)
  - CORS allowlist (env-driven; no wildcard in production)
  - Per-IP rate limiting

Anything that ever touches an API key passes through here. Audit by grepping
for "X-OpenAI-Api-Key" — these are the only places it should appear.
"""
from __future__ import annotations
import os
import re
import logging
from typing import Annotated

from fastapi import Header, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


# --------------------------------------------------------------------------
# 1. Header-based BYOK
# --------------------------------------------------------------------------

# Pattern matches any OpenAI-style key in error strings (sk-xxx / sk-proj-xxx)
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}", re.IGNORECASE)


def get_user_api_key(
    x_openai_api_key: Annotated[
        str | None,
        Header(alias="X-OpenAI-Api-Key", convert_underscores=False),
    ] = None,
) -> str | None:
    """FastAPI dependency that pulls the BYOK header.

    Returns the user-supplied key, or None if not provided. Endpoints that
    require a key should check the resolved key (header > env) and 401 if
    absent. The raw value is never logged here.
    """
    return x_openai_api_key


def resolve_api_key(user_key: str | None) -> str | None:
    """Resolution order: user header > env var. Empty string is treated as None.

    In a public BYOK deploy, env var is unset, so a missing header => None.
    In a self-hosted deploy with `OPENAI_API_KEY` set, the env value is used.
    """
    user_key = (user_key or "").strip() or None
    if user_key:
        return user_key
    env_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    return env_key or None


def require_api_key(user_key: str | None) -> str:
    """Resolve the key or raise 401 with a clear hint."""
    key = resolve_api_key(user_key)
    if not key:
        raise HTTPException(
            status_code=401,
            detail=(
                "OpenAI API key required. Set it in Settings → API key "
                "(stored only in your browser)."
            ),
        )
    return key


def sanitize_error(text: str | object) -> str:
    """Strip any `sk-...` token that might have leaked into an error payload.

    Used before any error message crosses the wire back to the client.
    """
    if text is None:
        return ""
    s = str(text)
    return _SK_PATTERN.sub("[REDACTED]", s)


# --------------------------------------------------------------------------
# 2. Security response headers
# --------------------------------------------------------------------------

def _csp_header(connect_src_extra: str = "") -> str:
    """Strict CSP. `connect_src` self-only — backend never makes the user's
    browser fetch from a 3rd party. `script-src self` blocks inline + CDN
    scripts. `frame-ancestors none` is the modern X-Frame-Options DENY."""
    parts = [
        "default-src 'self'",
        "script-src 'self'",
        # Inline styles allowed for Vite/HMR-built CSS and Tailwind atomic
        # classes. Production builds can tighten this further with a nonce.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        f"connect-src 'self' {connect_src_extra}".strip(),
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the production-grade security header set to every response."""

    def __init__(self, app: ASGIApp, csp_connect_extra: str = "") -> None:
        super().__init__(app)
        self.csp = _csp_header(csp_connect_extra)

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Block XSS via injected scripts, framing attacks, and inline content.
        response.headers.setdefault("Content-Security-Policy", self.csp)
        # 2 years HSTS + preload list eligibility.
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        # Disable powerful features we don't use.
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), interest-cohort=()",
        )
        # Defense-in-depth against MIME sniffing and XS-leaks.
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response


# --------------------------------------------------------------------------
# 3. Log redaction
# --------------------------------------------------------------------------

class _SensitiveHeaderFilter(logging.Filter):
    """Mutates uvicorn access-log messages so any 'sk-...' substring is masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            try:
                record.args = tuple(
                    _SK_PATTERN.sub("[REDACTED]", str(a)) for a in record.args
                )
            except Exception:
                pass
        if isinstance(record.msg, str):
            record.msg = _SK_PATTERN.sub("[REDACTED]", record.msg)
        return True


def install_log_redaction() -> None:
    """Attach the redaction filter to all relevant loggers.

    Belt-and-braces: the X-OpenAI-Api-Key header is NOT in default uvicorn
    access logs (only the request line is). This filter exists to scrub any
    accidental leak via Python's exception machinery or future log statements.
    """
    flt = _SensitiveHeaderFilter()
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", ""):
        logging.getLogger(name).addFilter(flt)


# --------------------------------------------------------------------------
# 4. CORS allowlist
# --------------------------------------------------------------------------

def get_cors_origins() -> list[str]:
    """Read ALLOWED_ORIGINS from env. Empty/unset => dev defaults (localhost)."""
    raw = (os.getenv("ALLOWED_ORIGINS") or "").strip()
    if not raw:
        # Vite dev defaults. Production must set ALLOWED_ORIGINS explicitly.
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    return [o.strip() for o in raw.split(",") if o.strip()]


# --------------------------------------------------------------------------
# 5. Rate limiting
# --------------------------------------------------------------------------

# slowapi gives us a battle-tested per-IP rate limiter as a FastAPI dep.
# Limits are intentionally generous for genuine pharma users, tight enough
# to make brute-force key probing pointless.
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
except Exception:  # pragma: no cover — slowapi missing in dev
    limiter = None
