# Security & Privacy

LitExtract is open source and uses a **bring-your-own-key (BYOK)** model
for OpenAI API access. This document describes how keys are handled and
the threat model the implementation defends against.

## Where your API key lives

| Location | Stored? |
|---|---|
| Your browser (`localStorage` or `sessionStorage`) | **Yes** — under the namespaced key `litextract.openai_key` |
| HTTP request header (in flight, TLS-encrypted) | **Yes** — for the duration of one request, as `X-OpenAI-Api-Key` |
| LitExtract backend memory | **Yes** — for ~60s during a single extraction; garbage-collected after the response |
| LitExtract backend database | No |
| LitExtract backend file system | No |
| LitExtract backend logs | No (redacted by middleware) |
| LitExtract backend env vars | Only when self-hosted with `OPENAI_API_KEY` set; never written by code |

The single sources of truth in code:

- Frontend: `frontend/src/lib/apiKey.ts` — only file that reads/writes
  `localStorage["litextract.openai_key"]`.
- Backend: `api/security.py` — only file that reads the
  `X-OpenAI-Api-Key` header.

You can audit the codebase by grepping for those identifiers.

## What the backend promises

1. The `X-OpenAI-Api-Key` header is **never** persisted to disk, database,
   or logs.
2. A log-redaction middleware scrubs any `sk-...` substring from access
   logs and error messages before they leave the process.
3. Each upload constructs a **fresh, per-request** LLM client; the key is
   not cached in any shared state and is dropped when the request handler
   returns.
4. Error responses sent to the browser are sanitized — any `sk-...` token
   that might leak through OpenAI's own error payloads is replaced with
   `[REDACTED]` before transmission.
5. CORS is locked to an explicit origin allowlist
   (`ALLOWED_ORIGINS` env var); no `*` wildcard in production.
6. Rate limiting (per IP) applies to `/api/upload` and `/api/test-key` to
   prevent brute-force key probing.

## Security headers on every response

| Header | Value |
|---|---|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; ...; frame-ancestors 'none'` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), interest-cohort=()` |
| `Cross-Origin-Resource-Policy` | `same-origin` |

The CSP is strict-by-default: no inline scripts, no third-party scripts,
no remote fonts, no data exfiltration via `connect-src` to other origins.

## Threat model & mitigations

| Threat | Mitigation |
|---|---|
| **XSS on our domain steals localStorage** | Strict CSP (`script-src 'self'`); no `dangerouslySetInnerHTML`; pinned dependencies; `npm audit` in CI. **Residual risk: a vulnerable dependency could allow injected code on our origin.** |
| **TLS downgrade / MITM** | `Strict-Transport-Security` with preload eligibility; deploy platforms must enforce HTTPS. |
| **Backend log scraping** | Header is never logged; redaction filter on uvicorn loggers as defence-in-depth. |
| **Backend memory dump** | Per-request scope; key dropped from memory after request handler returns. Upper bound on exposure: ~60 seconds. |
| **CSRF** | No cookies/sessions used; CORS allowlist; rate limiting. |
| **Clickjacking** | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'`. |
| **Supply-chain attack via npm/pip** | `package-lock.json` and `requirements.txt` pin versions; recommend Dependabot in deployed forks. |
| **Browser extension reads localStorage** | Documented user risk — extensions on the user's browser can read any localStorage on origins they have access to. Out of our control. |
| **Phishing clone of LitExtract** | User error — verify the domain. |
| **Plaintext key on disk** | Documented in the Settings UI; user can opt out via "Don't remember me" (`sessionStorage` only — forgotten on tab close). |

## What we explicitly don't do

- **Encrypted-at-rest in localStorage**: without a user-supplied passphrase,
  the encryption key would have to live in JS too — security theater. A
  passphrase-based scheme like MetaMask works but kills UX for a tool that
  runs many short tasks. We chose plain text + clear documentation.
- **Server-side key storage**: would require user accounts, key encryption
  with a server-held master key, and breach liability. Right answer when
  LitExtract grows a multi-tenant enterprise tier; wrong for OSS BYOK.
- **HttpOnly cookies for the key**: would mean JS can't read it — defeats
  the point of BYOK.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security bugs.

Send a description (and proof-of-concept if available) to the maintainer
via email or GitHub Security Advisories (private). We aim to respond
within 72 hours and ship a fix or mitigation within 14 days for high-
severity issues.

## Auditable trail

These are the only code paths where the key is touched:

```
frontend/
  src/lib/apiKey.ts           # localStorage read/write
  src/lib/api.ts              # authHeaders() — adds the header to fetch
  src/components/ApiKeyForm.tsx
  src/components/ApiKeyModal.tsx

backend/
  api/security.py             # header parsing, redaction, sanitization
  api/main.py                 # one require_api_key() call in /api/upload
                              # one Depends(get_user_api_key) in /api/test-key
  llm_wrapper.py              # accepts api_key= override
  pipeline_local.py           # accepts api_key= in constructor
```

Any file outside this list that handles the key is a bug. Please report it.
