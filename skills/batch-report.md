Print a post-batch corpus status report from the SQLite DB. Run the steps below in order.

---

## STEP 1 — Query the DB

Run this with the Bash tool:

```bash
cd c:/dev/biomarkerv1/v5-biomarker-rag-claude && python << 'PYEOF'
import sqlite3, json
from collections import defaultdict
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

conn = sqlite3.connect('db/extraction_state.db')
conn.row_factory = sqlite3.Row

# Latest run per paper
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
    ORDER BY run_datetime DESC
""").fetchall()

# Papers run in the last batch (last 24h)
recent_cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
recent = [r for r in papers if r['run_datetime'] and r['run_datetime'] >= recent_cutoff]

total = len(papers)
avg_f1   = sum((r['F1'] or 0) for r in papers) / total if total else 0
above70  = sum(1 for r in papers if (r['F1'] or 0) >= 70)
below70  = [r for r in papers if (r['F1'] or 0) < 70]

# Per-sheet averages
avg_bm_det  = sum(r['BM_Details']    or 0 for r in papers) / total
avg_study   = sum(r['Study_Results'] or 0 for r in papers) / total
avg_bm_res  = sum(r['BM_Results']    or 0 for r in papers) / total
avg_infer   = sum(r['Inferences']    or 0 for r in papers) / total

# Total cost
total_cost = sum(r['cost_usd_per_paper'] or 0 for r in papers)

# By disease
disease_f1 = defaultdict(list)
for r in papers:
    disease_f1[r['disease'] or 'unknown'].append(r['F1'] or 0)
by_disease = {d: (round(sum(v)/len(v),1), len(v)) for d,v in sorted(disease_f1.items())}

# By confidence
conf_counts = defaultdict(int)
for r in papers:
    conf_counts[r['confidence'] or 'unknown'] += 1

# Sort all papers by F1
sorted_asc = sorted(papers, key=lambda r: r['F1'] or 0)

print('=== CORPUS SUMMARY ===')
print(f'total={total}')
print(f'avg_f1={avg_f1:.1f}')
print(f'above70={above70}')
print(f'below70_count={len(below70)}')
print(f'avg_bm_det={avg_bm_det:.1f}')
print(f'avg_study={avg_study:.1f}')
print(f'avg_bm_res={avg_bm_res:.1f}')
print(f'avg_infer={avg_infer:.1f}')
print(f'total_cost_usd={total_cost:.2f}')
print(f'recent_count={len(recent)}')

print()
print('=== BY DISEASE ===')
for d,(f,n) in by_disease.items():
    bar = '#' * int(f/5)
    status = 'OK' if f >= 70 else 'LOW'
    print(f'  {d:<28} {f:5.1f}%  ({n} papers)  {bar}  [{status}]')

print()
print('=== BY CONFIDENCE ===')
for c in ['HIGH','MEDIUM','LOW','unknown']:
    n = conf_counts.get(c, 0)
    if n:
        print(f'  {c:<10} {n} papers')

print()
print('=== PER-SHEET AVERAGES ===')
print(f'  BM_Details:    {avg_bm_det:.1f}%')
print(f'  Study_Details: {avg_study:.1f}%')
print(f'  BM_Results:    {avg_bm_res:.1f}%')
print(f'  Inferences:    {avg_infer:.1f}%')

print()
print('=== BELOW 70% TARGET (worst first) ===')
for r in sorted_asc:
    if (r['F1'] or 0) < 70:
        ts = r['run_datetime'] or ''
        disease = (r['disease'] or 'unknown')[:20]
        conf = r['confidence'] or '-'
        print(f'  {r["pubmed_id"]}  F1={r["F1"] or 0:5.1f}%  disease={disease:<20}  conf={conf:<6}  run={ts[:16]}')

print()
print('=== TOP 5 PAPERS ===')
for r in reversed(sorted_asc[-5:]):
    print(f'  {r["pubmed_id"]}  F1={r["F1"] or 0:5.1f}%  disease={r["disease"] or "unknown"}')

print()
if recent:
    print(f'=== RECENTLY RUN ({len(recent)} papers in last 24h) ===')
    for r in recent:
        ts_utc = r['run_datetime'] or ''
        disease = (r['disease'] or 'unknown')[:20]
        conf = r['confidence'] or '-'
        f1 = r['F1'] or 0
        flag = ' <-- below target' if f1 < 70 else ''
        print(f'  {r["pubmed_id"]}  F1={f1:5.1f}%  disease={disease:<20}  conf={conf:<6}  run={ts_utc[:16]}{flag}')
else:
    print('=== RECENTLY RUN ===')
    print('  No papers run in the last 24h.')

print()
print(f'=== CORPUS COST ===')
print(f'  Total accumulated cost: ${total_cost:.2f}  ({total} papers @ ~${total_cost/total:.4f}/paper avg)')

conn.close()
PYEOF
```

---

## STEP 2 — Present the results

Read the printed output and present it as a clean, readable markdown summary with sections:

1. **Corpus Summary** — total extracted, avg F1, above/below 70% count, total cost
2. **Per-Sheet Averages** — BM_Details / Study_Details / BM_Results / Inferences
3. **By Disease** — table of disease, count, avg F1, status (OK / needs work)
4. **Confidence Breakdown** — HIGH / MEDIUM / LOW counts
5. **Below 70% Papers** — sorted worst-first, showing PMID, F1, disease, confidence, last run time
6. **Top 5 Papers** — best-performing PMIDs
7. **Recent Batch** — papers run in last 24h with F1 and flag if below target
8. **Cost Summary** — total cost and average per paper

Keep the output concise. Use bold for key numbers. Flag papers below 70% clearly.
Note: DB timestamps are UTC; local time is UTC+5:30 (IST).
Note: Paper 34975751 is NOT in goldset_1k — its 0% gold score is a false negative; ignore it.
