Generate a comprehensive project handoff document for the Biomarker RAG pipeline. This captures the full current state — corpus scores, architecture, recent changes, open items, and exact commands to resume — so any teammate or a new Claude Code session can pick up the work without losing context.

If the user provided text after /handoff, treat it as a freetext note to embed in the "Session Notes" section (e.g. /handoff "switched to gpt-5.4-mini, reverted to gpt-4o-mini after comparison").

---

## STEP 1 — Determine output filename

Use today's date (YYYYMMDD format) to build:
  filename = handoff_YYYYMMDD.md
  save_path = c:/dev/biomarkerv1/v5-biomarker-rag-claude/docs/handoffs/{filename}

If the docs/handoffs/ directory does not exist, create it (use Bash: mkdir -p).

If a file with today's date already exists, overwrite it — this is always the latest snapshot.

---

## STEP 2 — Gather all data in parallel

Run ALL of the following simultaneously (parallel tool calls):

### 2A — Live corpus stats (Bash)

```bash
cd c:/dev/biomarkerv1/v5-biomarker-rag-claude && python << 'PYEOF'
import sqlite3, json
from collections import defaultdict
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('db/extraction_state.db')
conn.row_factory = sqlite3.Row

papers = conn.execute("""
    SELECT pubmed_id, F1, Row_Recall, Field_Precision,
           BM_Details, Study_Results, BM_Results, Inferences,
           disease, study_types, bm_types, confidence,
           bm_results_count, bm_details_count, cost_usd_per_paper,
           run_datetime, prompt_hash
    FROM runs_openai
    WHERE pubmed_id != 'Avg'
      AND (pubmed_id, run_datetime) IN (
          SELECT pubmed_id, MAX(run_datetime) FROM runs_openai
          WHERE pubmed_id != 'Avg' GROUP BY pubmed_id
      )
    ORDER BY F1 ASC
""").fetchall()

total = len(papers)
avg_f1  = sum((r['F1'] or 0) for r in papers) / total if total else 0
above70 = sum(1 for r in papers if (r['F1'] or 0) >= 70)
avg_bm_det = sum(r['BM_Details']    or 0 for r in papers) / total
avg_study  = sum(r['Study_Results'] or 0 for r in papers) / total
avg_bm_res = sum(r['BM_Results']    or 0 for r in papers) / total
avg_infer  = sum(r['Inferences']    or 0 for r in papers) / total
total_cost = sum(r['cost_usd_per_paper'] or 0 for r in papers)

disease_f1 = defaultdict(list)
for r in papers:
    disease_f1[r['disease'] or 'unknown'].append(r['F1'] or 0)
by_disease = {d: (round(sum(v)/len(v),1), len(v)) for d,v in sorted(disease_f1.items())}

sorted_asc = list(papers)  # already sorted by F1 ASC
below70 = [r for r in sorted_asc if (r['F1'] or 0) < 70]

# LLM comparison table
try:
    llm_rows = conn.execute("""
        SELECT pubmed_id, llm_name, f1_score, cost_usd, run_datetime
        FROM LLM_comparison
        ORDER BY pubmed_id, run_datetime
    """).fetchall()
except Exception:
    llm_rows = []

# Latest prompt hashes
hashes = conn.execute("""
    SELECT DISTINCT prompt_hash, disease, COUNT(*) as cnt
    FROM runs_openai
    WHERE prompt_hash IS NOT NULL
    GROUP BY prompt_hash, disease
    ORDER BY cnt DESC
    LIMIT 10
""").fetchall()

print('=== CORPUS ===')
print(f'total={total}')
print(f'avg_f1={avg_f1:.2f}')
print(f'above70={above70}')
print(f'below70={len(below70)}')
print(f'avg_bm_det={avg_bm_det:.2f}')
print(f'avg_study={avg_study:.2f}')
print(f'avg_bm_res={avg_bm_res:.2f}')
print(f'avg_infer={avg_infer:.2f}')
print(f'total_cost={total_cost:.2f}')

print()
print('=== BY DISEASE ===')
for d,(f,n) in by_disease.items():
    print(f'{d}|{f}|{n}')

print()
print('=== BELOW 70 ===')
for r in below70:
    print(f'{r["pubmed_id"]}|{r["F1"] or 0:.1f}|{r["disease"] or "unknown"}|{r["confidence"] or "-"}|{(r["run_datetime"] or "")[:16]}')

print()
print('=== TOP 10 ===')
for r in reversed(sorted_asc[-10:]):
    print(f'{r["pubmed_id"]}|{r["F1"] or 0:.1f}|{r["disease"] or "unknown"}')

print()
print('=== LLM COMPARISON ===')
for r in llm_rows:
    print(f'{r["pubmed_id"]}|{r["llm_name"]}|{r["f1_score"]:.1f}|{r["cost_usd"]:.4f}|{(r["run_datetime"] or "")[:16]}')

print()
print('=== PROMPT HASHES ===')
for r in hashes:
    print(f'{r["prompt_hash"]}|{r["disease"] or "unknown"}|{r["cnt"]}')

conn.close()
PYEOF
```

### 2B — Read current .env state (Read tool)
Read file: `c:/dev/biomarkerv1/v5-biomarker-rag-claude/.env`

### 2C — Read MEMORY.md for recent session history (Read tool)
Read file: `C:/Users/prabhu.pandian/.claude/projects/c--dev-biomarkerv1-v5-biomarker-rag-claude/memory/MEMORY.md`

### 2D — List all prompt addon folders (Bash)
```bash
cd c:/dev/biomarkerv1/v5-biomarker-rag-claude && python << 'PYEOF'
import os, hashlib

def file_hash(path):
    try:
        return hashlib.md5(open(path,'rb').read()).hexdigest()[:8]
    except:
        return '????????'

for root, dirs, files in os.walk('prompts'):
    dirs.sort()
    for f in sorted(files):
        if f.endswith('.txt'):
            p = os.path.join(root, f)
            h = file_hash(p)
            size = os.path.getsize(p)
            print(f'{p}  [{h}]  {size}b')
PYEOF
```

### 2E — Check for any in-progress or recent Python processes / open tasks (Bash)
```bash
cd c:/dev/biomarkerv1/v5-biomarker-rag-claude && python << 'PYEOF'
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('db/extraction_state.db')

# Most recent 5 runs
recent = conn.execute("""
    SELECT pubmed_id, F1, disease, run_datetime, prompt_hash
    FROM runs_openai
    WHERE pubmed_id != 'Avg'
    ORDER BY run_datetime DESC
    LIMIT 5
""").fetchall()

print('=== LAST 5 DB WRITES ===')
for r in recent:
    print(f'{r[0]}  F1={r[1] or 0:.1f}%  disease={r[2] or "?"}  run={r[3][:16] if r[3] else "?"}  hash={r[4] or "?"}')

# Check extraction_log for latest cost + model
try:
    logs = conn.execute("""
        SELECT pubmed_id, model, cost_usd, run_datetime, study_types, disease, bm_types
        FROM extraction_log
        ORDER BY run_datetime DESC
        LIMIT 5
    """).fetchall()
    print()
    print('=== LAST 5 EXTRACTION LOGS ===')
    for r in logs:
        print(f'{r[0]}  model={r[1]}  cost=${r[2] or 0:.4f}  disease={r[5] or "?"}  run={r[3][:16] if r[3] else "?"}')
except Exception as e:
    print(f'extraction_log error: {e}')

conn.close()
PYEOF
```

---

## STEP 3 — Compose the handoff document

Using ALL gathered data, write the file at `docs/handoffs/handoff_YYYYMMDD.md`.

The document MUST include all sections below. Write it so a teammate with no prior context can read it top-to-bottom and immediately understand the system, its current state, and what to do next. Use concrete numbers everywhere — never say "good progress", say "72.3% avg F1, 171/228 above 70%".

---

### Document structure

```
# Biomarker RAG Pipeline — Project Handoff
**Generated:** YYYY-MM-DD HH:MM IST
**Author:** [leave blank — filled by user]
**Branch/Workspace:** c:/dev/biomarkerv1/v5-biomarker-rag-claude

---

## 1. What This System Does (30-second summary)

[2-3 sentences: PDFs → Azure DI → LLM agents → structured biomarker data → Excel + SQLite.
Mention the 4 data types. Mention gold standard verification.]

---

## 2. Current Corpus Status

| Metric | Value |
|--------|-------|
| Papers extracted | N |
| Average F1 | XX.X% |
| Above 70% target | N / N (XX%) |
| Below 70% | N papers |
| Total extraction cost | $XX.XX |

### Per-Sheet F1 Averages
| Sheet | Avg F1 |
|-------|--------|
| Study_Details | XX.X% |
| BM_Details | XX.X% |
| BM_Results | XX.X% |
| Inferences | XX.X% |

### By Disease
| Disease | Papers | Avg F1 | Status |
|---------|--------|--------|--------|
[fill from DB data — mark LOW if < 70%]

---

## 3. Active LLM Configuration

**Current model (production):** [from .env OPENAI_COMPLETION_MODEL]
**Provider:** [from .env LLM_PROVIDER]
**Embeddings:** [from .env EMBEDDING_MODEL]

To switch models, change `.env`:
- `LLM_PROVIDER=openai` + `OPENAI_COMPLETION_MODEL=gpt-4o-mini`  → production
- `LLM_PROVIDER=openai` + `OPENAI_COMPLETION_MODEL=gpt-5.4-mini` → comparison run
- `LLM_PROVIDER=anthropic` + `ANTHROPIC_COMPLETION_MODEL=claude-sonnet-4-5` → Claude run

### LLM Comparison Results (5 focus papers)
[fill from LLM_comparison table — per-model avg F1 + total cost]

| Model | Avg F1 | Total Cost (5 papers) | Notes |
|-------|:------:|:---------------------:|-------|
[rows from LLM_comparison grouped by model]

---

## 4. Pipeline Architecture

```
PDF (Azure Blob)
  → Azure Document Intelligence (prebuilt-layout)
  → DI JSON (di-output blob container)
  → document_loader.py (loads from blob)
  → table_parser.py (markdown tables → Row N: Col=Val format)
  → study_classifier.py (detect disease / study type / bm type)
  → prompt_composer.py (assemble 4-level prompt hierarchy)
  → 4 agents (study_details / bm_details / bm_results / inferences)
  → excel_handler.py → biomarker-cl-out.xlsx
  → verification_agent.py → F1/Recall/Precision vs goldset_1k.xlsx
  → init_db.py → db/extraction_state.db (runs_openai + extraction_log)
```

### Key Files
| File | Role |
|------|------|
| run_paper.py | CLI: single paper or batch |
| run_with_training.py | Training loop: extract → verify → improve |
| main.py | BiomarkerExtractionPipeline orchestrator |
| agents/base_agent.py | Base LLM call + eval loop |
| agents/bm_results_agent.py | BM_Results (3 parallel workers) |
| verification_agent.py | Gold standard comparison, 8 normalizers |
| prompt_composer.py | 4-level prompt assembly + hash |
| training_loop.py | Auto prompt improvement when F1 < 70% |
| llm_wrapper.py | Multi-provider routing (openai/anthropic/azure) |
| study_classifier.py | Disease (17) + study type (5) + bm type (3) |

### Prompt Hierarchy (4 levels)
```
prompts/core/<agent>_core.txt          ← always included
prompts/diseases/<disease>/            ← appended when disease detected
prompts/study_types/<type>/            ← appended when study type detected
prompts/bm_types/<type>/               ← appended when bm type detected (cellular/lncrna/composite_score)
```

[List all active prompt folders with their file hashes from Step 2D]

---

## 5. Recent Changes (this session / this week)

[Summarize changes from MEMORY.md — verification fixes, prompt changes, normalizer additions.
Be specific: "Added _normalize_outcome entry: 'complete remission' → 'complete response'" not "improved normalization".]

Key sessions:
- [Date]: [What changed] → [impact in F1 points if known]
- [Date]: [What changed] → [impact]

---

## 6. Papers Below 70% — Priority List

[Full list from DB, sorted worst-first. Note which are not-in-goldset (34975751, 34446577, 34717747, 34250747, 35855852, 35733776, 32016671, 33613554) and should be excluded from priority work.]

| PMID | F1 | Disease | Confidence | Last Run | Note |
|------|----|---------|------------|----------|------|
[fill from below70 list — mark not-in-goldset papers]

---

## 7. Known Issues & Special Cases

| Issue | Status | Workaround |
|-------|--------|------------|
| OpenMP conflict (Windows) | Active | Prefix with `KMP_DUPLICATE_LIB_OK=TRUE` |
| 34975751 not in goldset | Active | Ignore gold score; internal scores 87-91% |
| 33850056, 33658501, 33300278 at 0% | Uninvestigated | Needs root cause analysis |
| gastric_cancer avg 19.1% (3×0%) | Active | Most are not-in-goldset; check 33300278 |
| Claude/gpt-5.4-mini JSON truncation | Active | 8192 / 32k output limits; fix: paginate BM_Results |
| BM_Results ceiling at 58.3% | Active | Row-level recall is main bottleneck |

---

## 8. How to Resume Work

### Quick health check
```bash
python -c "
import sqlite3
conn = sqlite3.connect('db/extraction_state.db')
rows = conn.execute('SELECT COUNT(*), AVG(F1) FROM (SELECT pubmed_id, MAX(F1) as F1 FROM runs_openai WHERE pubmed_id!=\'Avg\' GROUP BY pubmed_id)').fetchone()
print(f'{rows[0]} papers, Avg F1: {rows[1]:.1f}%')
conn.close()
"
```

### Re-run a single paper
```bash
python run_paper.py <PMID> --force
```

### Verify only (no LLM cost — just re-score)
```bash
python run_paper.py <PMID> --verify-only
```

### Run a full batch with training loop (deferred mode)
```bash
KMP_DUPLICATE_LIB_OK=TRUE python run_with_training.py --batch4 --deferred
```

### Generate updated presentation deck
```
/update-deck
```

### Add new papers to corpus
```bash
python docintel_process/download_papers.py --pmid-file docintel_process/new_pmids.txt
python docintel_process/process_docs.py --pmid-file docintel_process/new_pmids.txt
# add PMIDs to config.py BATCH list
KMP_DUPLICATE_LIB_OK=TRUE python run_with_training.py --batch4 --deferred
```

---

## 9. Suggested Next Steps

[Based on the current state, list 3-5 concrete, prioritized actions. Be specific about which papers/diseases/prompts to target. Derive these from the data — don't make up generic advice.]

Examples (replace with actual current priorities):
1. Investigate 33850056, 33658501, 33300278 (0% F1, HIGH confidence) — run verify-only and inspect gold vs extracted to find root cause
2. Target liver_cancer avg F1 (68%) — analyze 5 worst liver papers for common failure pattern, then improve prompts/normalizers generically
3. Run /update-deck to publish current 228-paper results for stakeholder review
4. Explore BM_Results row-recall improvements — current ceiling is 58.3%; pagination approach may help complex papers

---

## 10. Environment Setup (for new workspace)

```
# Required .env keys:
DOCUMENTINTELLIGENCE_ENDPOINT=...
DOCUMENTINTELLIGENCE_API_KEY=...
AZURE_STORAGE_CONNECTION_STRING=...
OPENAI_API_KEY=...
OPENAI_COMPLETION_MODEL=gpt-4o-mini
LLM_PROVIDER=openai
ANTHROPIC_API_KEY=...           # only for Claude comparison runs
ANTHROPIC_COMPLETION_MODEL=claude-sonnet-4-5
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_PROVIDER=openai
USE_EMBEDDINGS=true
TRAINING_MODE=true
INPUT_CONTAINER=biomarker-ragcontainer
OUTPUT_CONTAINER=di-output
```

Install deps: `pip install -r requirements.txt`
DB auto-migrates on first run (init_db.py).

---

## 11. Session Notes

[If the user provided a note after /handoff, include it here verbatim. Otherwise leave this section as: "No session notes provided."]

---

*Generated by /handoff skill. Refresh anytime with `/handoff` or `/handoff "your note here"`.*
```

---

## STEP 4 — Write the file

Use the Write tool to save the composed document to `docs/handoffs/handoff_YYYYMMDD.md`.

Make sure all sections have real data filled in — no placeholder text like "[fill from DB]" should remain in the output file. Every table cell, every number, every list must be populated from the actual gathered data.

---

## STEP 5 — Confirm to the user

Print a short confirmation:

```
Handoff document saved to docs/handoffs/handoff_YYYYMMDD.md

Snapshot: N papers | Avg F1 XX.X% | N above 70% | $XX.XX total cost
Active model: [model name] via [provider]
Open items: N papers below 70% target

Share this file with your team or open it in a new Claude Code session to resume.
```
