Scan the Biomarker Extract project for files and folders that are no longer needed and remove them. Follow ALL steps below in order.

---

## STEP 1 — Scan for stale files

Run the following with the Bash tool to list candidates:

```bash
cd c:/dev/biomarkerv1/v5-biomarker-rag-claude && echo "=== __pycache__ ===" && find . -name "__pycache__" -type d && echo "=== *.pyc ===" && find . -name "*.pyc" && echo "=== Temp / scratch files ===" && find . -maxdepth 2 \( -name "*.tmp" -o -name "*.bak" -o -name "*.log" -o -name "scratch_*.py" -o -name "test_*.py" -o -name "debug_*.py" -o -name "check_*.py" -o -name "investigate_*.py" -o -name "compare_*.py" -o -name "analyze_*.py" \) && echo "=== Old Excel backups ===" && find . -name "*.xlsx.bak" -o -name "*_backup*.xlsx" -o -name "*_old*.xlsx" && echo "=== docintel_process temp ===" && ls docintel_process/_download_tmp 2>/dev/null || echo "(none)" && ls docintel_process/logs 2>/dev/null || echo "(none)" && echo "=== Old report scripts ===" && find . -maxdepth 1 -name "report_*.py" && echo "=== docs/presentations old versions ===" && find docs/presentations -name "biomarker_deck_v*.html" | sort
```

---

## STEP 2 — Show the deletion plan

Before deleting anything, print a clear list of everything that will be removed, grouped by category:

```
DELETION PLAN
=============
__pycache__ / .pyc:
  <list>

Temp / scratch / one-off scripts:
  <list>

Old Excel backups:
  <list>

docintel_process temp:
  <list>

Old versioned HTML decks (keep latest 2 only):
  <list of files older than latest 2>

Nothing found in a category → print "(none)"
```

Ask the user: "Proceed with deletion? (yes/no)"

Wait for user confirmation before proceeding to STEP 3.

---

## STEP 3 — Delete confirmed items

Only after user confirms, execute deletions using the Bash tool:

```bash
# __pycache__ and .pyc
find c:/dev/biomarkerv1/v5-biomarker-rag-claude -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find c:/dev/biomarkerv1/v5-biomarker-rag-claude -name "*.pyc" -delete 2>/dev/null

# Temp / scratch scripts at root level
# (list them explicitly from Step 1 output — never use wildcard rm on .py files)

# Old Excel backups
# (list explicitly)

# docintel_process temp
rm -rf c:/dev/biomarkerv1/v5-biomarker-rag-claude/docintel_process/_download_tmp 2>/dev/null
rm -rf c:/dev/biomarkerv1/v5-biomarker-rag-claude/docintel_process/logs 2>/dev/null
rm -f c:/dev/biomarkerv1/v5-biomarker-rag-claude/docintel_process/failed_download.txt 2>/dev/null
rm -f c:/dev/biomarkerv1/v5-biomarker-rag-claude/docintel_process/pipeline_status.json 2>/dev/null

# Old versioned HTML decks — keep latest 2, delete older ones
# (list explicitly from Step 1 sort output — never bulk delete all)
```

IMPORTANT RULES:
- NEVER delete any of these core files regardless of what the scan finds:
  main.py, run_paper.py, run_with_training.py, config.py, column_mappings.py,
  excel_handler.py, document_loader.py, init_db.py, llm_wrapper.py,
  prompt_composer.py, rag_system.py, study_classifier.py, table_parser.py,
  token_tracker.py, training_loop.py, verification_agent.py,
  verification_agent.py, base_agent.py, bm_details_agent.py,
  bm_results_agent.py, inferences_agent.py, study_details_agent.py,
  goldset_1k.xlsx, biomarker-cl-out.xlsx, extraction_state.db,
  requirements.txt, CLAUDE.md, README.md, Free_Full_Text.txt,
  download_papers.py, process_docs.py
- NEVER delete the entire prompts/ or db/ or agents/ or docs/ folder
- NEVER delete .env files
- For HTML decks: always keep the 2 most recent versions

---

## STEP 4 — Confirm to user

After deletion, print:

```
Cleanup complete.
Removed: <count> items
Kept clean: core pipeline, prompts, db, agents, docs/presentations (latest 2 decks)
```
