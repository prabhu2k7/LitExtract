---
title: Biomarker Research
emoji: 🧪
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
license: agpl-3.0
short_description: Structured biomarker extraction from oncology PDFs
---

# Biomarker Research — Oncology Extraction Platform

> Engineering codename: **LitExtract**. The codename appears in the GitHub
> URL, file paths, and commit history; the user-facing brand is **Biomarker
> Research**.

Open-source pipeline that turns oncology research papers into structured,
auditable biomarker data. Drop a PDF, get back a 4-sheet workbook with
study details, biomarker catalog, statistical results, and author
inferences — every row tagged with a verbatim source quote.

[![Live demo](https://img.shields.io/badge/Live%20demo-Hugging%20Face%20Spaces-yellow?logo=huggingface)](https://huggingface.co/spaces)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18-blue.svg)](https://react.dev/)

## What it does

**Pipeline:**

```
PDF (uploaded)
  → pymupdf4llm + pdfplumber (local extraction, no Azure dependency)
  → study_classifier  — disease + study type + biomarker type
  → prompt_composer   — 4-level prompt (core + disease + study + bm addons)
  → 4 specialized agents in parallel
  → Excel workbook · CSV · JSON · biomarker registry
```

**Four output sheets, every row source-cited:**

| Sheet | What it contains |
|---|---|
| **Study_Details** | Study design, disease, patient counts, demographics, geography, treatment regimen |
| **BM_Details** | Biomarker catalog: name, type (RNA / Protein / Genetic / Clinical / Composite), nature |
| **BM_Results** | Statistical findings: p-values, effect sizes, hazard ratios, CIs, specimen, methodology |
| **Inferences** | Author conclusions per biomarker — prognostic / diagnostic / predictive / monitoring |

## Quick start

### Option 1 — Run locally with Docker

```bash
git clone https://github.com/<your-username>/LitExtract.git
cd LitExtract
cp .env.example .env       # leave OPENAI_API_KEY blank for BYOK mode
docker compose up
```

Open <http://localhost:7860>. On first upload the UI will prompt for an
OpenAI API key — paste yours, it lives only in your browser.

### Option 2 — Try the hosted demo (BYOK)

Visit the live demo and bring your own OpenAI API key:
**[your-username-litextract.hf.space](https://huggingface.co/spaces)**

The demo runs on Hugging Face Spaces' free tier. Your key never leaves
your browser → backend → OpenAI loop; we never store it.

### Option 3 — Develop locally (no Docker)

Backend:
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload --port 8765
```

Frontend (separate terminal):
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api -> :8765
```

## Architecture

```
┌─────────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│  React (Vite, TS,   │    │  FastAPI             │    │  4 LLM agents    │
│  Tailwind v4,       │ ◄──┤  + per-request LLM   │ ◄──┤  (gpt-4o-mini    │
│  TanStack Query)    │    │  + security headers  │    │   default)       │
└─────────────────────┘    │  + rate limit        │    └──────────────────┘
       ▲                   │  + log redaction     │              │
       │ X-OpenAI-Api-Key  └──────────────────────┘              ▼
       │ (TLS, header                  │                ┌────────────────┐
       │  only, never                  ▼                │  Local PDF     │
       │  persisted)            ┌────────────┐          │  extractor     │
       │                        │  SQLite    │          │  (pymupdf4llm  │
   localStorage                 │  uploads + │          │   + pdfplumber)│
   (your browser)               │  runs DB   │          └────────────────┘
                                └────────────┘
```

## Features

- **4-agent extraction** with sub-stage progress (Reading PDF → Classifying →
  Extracting study/BM/results/inferences → Compiling)
- **Multi-file upload** queue with per-file ETA + cost
- **Force re-extract** flag bypasses the SHA256 cache; cache hits are free
- **Source citations** per row — verbatim quote + section ("Results", "Discussion", etc.)
- **3 export formats** — Excel (4 sheets), flat CSV (one row per finding,
  for pivots), full JSON
- **Biomarker registry** — corpus-wide cross-paper view with disease, sig
  rate, paper count
- **History** of every extraction with cost + duration
- **BYOK** — bring your own OpenAI key, stored only in the browser

## Security & Privacy

LitExtract uses **bring-your-own-key (BYOK)**: users paste their own
OpenAI API key in the UI; the LitExtract backend never persists it.

| | |
|---|---|
| Where the key lives | Your browser (`localStorage` or opt-in `sessionStorage`) |
| How it travels | TLS-encrypted `X-OpenAI-Api-Key` header on each upload |
| Backend persistence | Never (no DB, no file, no logs) |

**Hardening shipped:** strict CSP · HSTS preload · X-Frame-Options DENY ·
self-hosted Inter font (no Google Fonts) · per-IP rate limit · `sk-...`
redaction in error responses and logs · per-request LLM client scope.

For the full threat model, audit trail, and disclosure policy see
[SECURITY.md](SECURITY.md).

## Deploy your own copy

### Hugging Face Spaces (free, recommended)

1. Fork this repo to your GitHub
2. Create a new Hugging Face Space — choose **Docker** as the SDK
3. Add the GitHub repo URL as the source — HF auto-syncs and rebuilds
4. Open the Space URL — done

The `README.md` YAML frontmatter at the top of this file tells HF Spaces
how to build and run the image.

### Other platforms

The same `Dockerfile` runs on:
- **Render** — free web service tier (sleeps after 15 min idle)
- **Fly.io** — free tier with persistent volumes
- **Railway / Koyeb / any PaaS** that builds from a Dockerfile
- **Your own VPS** — `docker compose up`

Set these env vars in production:

```
OPENAI_API_KEY=                         # leave empty for BYOK
ALLOWED_ORIGINS=https://your-domain     # required, no wildcard
PORT=7860                               # most platforms inject this
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `azure-openai` |
| `OPENAI_API_KEY` | empty | Set = self-host mode · empty = BYOK |
| `OPENAI_COMPLETION_MODEL` | `gpt-4o-mini` | Lowest-cost OpenAI model that handles structured extraction |
| `ALLOWED_ORIGINS` | dev defaults | CORS allowlist (comma-separated) |
| `PORT` | `7860` | HTTP port (HF Spaces convention) |

Full list in [`.env.example`](.env.example).

## Cost — what you'll pay OpenAI per paper

Defaults (`gpt-4o-mini`):

| Paper size | Tokens | Cost |
|---|---|---|
| Short (synthetic, 2 pages) | ~30 K | ~$0.007 |
| Typical research paper (10–15 pages) | ~50 K | ~$0.011 |
| Long review paper (30+ pages) | ~150 K | ~$0.035 |

**1,000 papers ≈ $10–25.** Cache hits (same SHA256) are free.

Switch to `gpt-4o` (~16× cost) for higher accuracy on hard papers, or to
`claude-sonnet-4-5` for comparable quality. Set in `OPENAI_COMPLETION_MODEL`.

## Repo layout

| Path | Purpose |
|---|---|
| [`api/`](api/) | FastAPI backend (BYOK, security middleware, endpoints) |
| [`agents/`](agents/) | 4 extraction agents (study, biomarker, results, inferences) |
| [`prompts/`](prompts/) | 4-level prompt hierarchy (core + disease + study + bm addons) |
| [`pipeline_local.py`](pipeline_local.py) | UI-flow orchestrator (no Azure DI dependency) |
| [`pdf_extractor.py`](pdf_extractor.py) | Local PDF → text + structured tables |
| [`verification_agent.py`](verification_agent.py) | Gold-standard scoring (currently unused in UI flow) |
| [`frontend/`](frontend/) | Vite + React + Tailwind v4 SPA |
| [`Dockerfile`](Dockerfile) | Multi-stage build for any container PaaS |
| [`SECURITY.md`](SECURITY.md) | Threat model, audit trail, vulnerability disclosure |

## Contributing

PRs welcome. For the pipeline / agent code, please:
1. Run `python -c "import ast; ast.parse(open('api/main.py').read())"` — no syntax errors
2. Verify the React app builds: `cd frontend && npm run build`
3. Verify the Docker image builds: `docker build .`
4. Don't add a feature gated on a paid third-party service unless it's optional

For security issues, see [SECURITY.md](SECURITY.md) — **do not open a
public issue**.

## License

[GNU Affero General Public License v3.0](LICENSE).

The AGPL means: if you run a modified version of LitExtract as a service
others can use, you must publish your modifications under the AGPL too.
This keeps improvements flowing back to the open-source ecosystem. If
this licensing doesn't fit your use case, get in touch about a
commercial license.

## Acknowledgments

Built with [FastAPI](https://fastapi.tiangolo.com/),
[LangChain](https://www.langchain.com/),
[OpenAI](https://platform.openai.com/),
[Vite](https://vitejs.dev/),
[Tailwind CSS](https://tailwindcss.com/),
[shadcn/ui patterns](https://ui.shadcn.com/),
[Lucide icons](https://lucide.dev/),
[pymupdf4llm](https://pymupdf.readthedocs.io/),
[pdfplumber](https://github.com/jsvine/pdfplumber).
