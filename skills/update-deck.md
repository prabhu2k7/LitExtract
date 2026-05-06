Generate a new versioned HTML presentation deck for the Biomarker RAG Extraction Pipeline. Follow ALL steps below in order.

If the user provided arguments after /update-deck, those describe architecture changes to include as an extra card. If no arguments, this is a stats-only refresh.

---

## STEP 1 — Determine next version number

Use the Glob tool to find all files matching:
  c:/dev/biomarkerv1/v5-biomarker-rag-claude/docs/presentations/biomarker_deck_v*.html

Extract version numbers from filenames (e.g. biomarker_deck_v3_0325.html → 3).
Next version = highest found + 1. If no files exist, start at v1.

Get today's date in MMDD format (e.g. March 25 = 0325).

New filename = biomarker_deck_v{N}_{MMDD}.html
Save path = c:/dev/biomarkerv1/v5-biomarker-rag-claude/docs/presentations/{filename}

---

## STEP 2 — Pull live stats from DB

Run this with the Bash tool:

```bash
cd c:/dev/biomarkerv1/v5-biomarker-rag-claude && python << 'PYEOF'
import sqlite3, json
from collections import defaultdict
conn = sqlite3.connect('db/extraction_state.db')
conn.row_factory = sqlite3.Row

# Latest run per paper
papers = conn.execute("""
    SELECT pubmed_id, F1, Row_Recall, Field_Precision,
           BM_Details, Study_Results, BM_Results, Inferences,
           disease, study_types, bm_types,
           bm_results_count, bm_details_count, cost_usd_per_paper, run_datetime
    FROM runs_openai
    WHERE pubmed_id != 'Avg'
      AND (pubmed_id, run_datetime) IN (
          SELECT pubmed_id, MAX(run_datetime) FROM runs_openai
          WHERE pubmed_id != 'Avg' GROUP BY pubmed_id
      )
    ORDER BY run_datetime ASC
""").fetchall()

total = len(papers)
avg_f1 = sum((r['F1'] or 0) for r in papers) / total if total else 0
above70 = sum(1 for r in papers if (r['F1'] or 0) >= 70)
sorted_f1 = sorted(papers, key=lambda r: r['F1'] or 0)
top5 = [(r['pubmed_id'], round(r['F1'] or 0, 1)) for r in sorted_f1[-5:][::-1]]
bot5 = [(r['pubmed_id'], round(r['F1'] or 0, 1)) for r in sorted_f1[:5]]

# Per-sheet averages
avg_bm_det  = sum(r['BM_Details'] or 0 for r in papers) / total
avg_study   = sum(r['Study_Results'] or 0 for r in papers) / total
avg_bm_res  = sum(r['BM_Results'] or 0 for r in papers) / total
avg_infer   = sum(r['Inferences'] or 0 for r in papers) / total

# By disease
disease_f1 = defaultdict(list)
for r in papers:
    if r['disease']: disease_f1[r['disease']].append(r['F1'] or 0)
by_disease = {d: (round(sum(v)/len(v),1), len(v)) for d,v in sorted(disease_f1.items())}

# By study type
stype_f1 = defaultdict(list)
for r in papers:
    stypes = json.loads(r['study_types']) if r['study_types'] else ['general']
    for st in stypes: stype_f1[st].append(r['F1'] or 0)
by_stype = {s: (round(sum(v)/len(v),1), len(v)) for s,v in sorted(stype_f1.items())}

# By BM type
bmt_f1 = defaultdict(list)
for r in papers:
    bmts = json.loads(r['bm_types']) if r['bm_types'] else ['none']
    for bt in bmts: bmt_f1[bt].append(r['F1'] or 0)
by_bmt = {bt: (round(sum(v)/len(v),1), len(v)) for bt,v in sorted(bmt_f1.items())}

# Full per-paper rows (processed order = run_datetime ASC)
all_papers = [(
    r['pubmed_id'],
    r['disease'] or 'unknown',
    json.loads(r['study_types']) if r['study_types'] else [],
    json.loads(r['bm_types']) if r['bm_types'] else [],
    round(r['F1'] or 0, 1),
    round(r['Row_Recall'] or 0, 1),
    round(r['Field_Precision'] or 0, 1),
    round(r['BM_Details'] or 0, 1),
    round(r['Study_Results'] or 0, 1),
    round(r['BM_Results'] or 0, 1),
    round(r['Inferences'] or 0, 1),
    r['bm_results_count'] or 0,
    round(r['cost_usd_per_paper'] or 0, 4),
) for r in papers]

print(f'extracted={total}')
print(f'avg_f1={avg_f1:.1f}')
print(f'above70={above70}')
print(f'top5={top5}')
print(f'bot5={bot5}')
print(f'avg_bm_det={avg_bm_det:.1f}')
print(f'avg_study={avg_study:.1f}')
print(f'avg_bm_res={avg_bm_res:.1f}')
print(f'avg_infer={avg_infer:.1f}')
print(f'by_disease={dict(by_disease)}')
print(f'by_stype={dict(by_stype)}')
print(f'by_bmt={dict(by_bmt)}')
print(f'all_papers={all_papers}')

# LLM comparison data
llm_rows = conn.execute("""
    SELECT pubmed_id, llm_name, embedding_model,
           study_details, bm_details, bm_results, inferences, f1_score, run_datetime
    FROM LLM_comparison
    ORDER BY pubmed_id, llm_name, run_datetime
""").fetchall()
llm_data = [(r['pubmed_id'], r['llm_name'], r['embedding_model'],
             round(r['study_details'] or 0,1), round(r['bm_details'] or 0,1),
             round(r['bm_results'] or 0,1), round(r['inferences'] or 0,1),
             round(r['f1_score'] or 0,1), (r['run_datetime'] or '')[:16]) for r in llm_rows]
# Summary per LLM
from collections import defaultdict as _dd
llm_summary = _dd(lambda: {'papers':0,'f1':[],'std':[],'bmd':[],'bmr':[],'inf':[],'embed':''})
for r in llm_rows:
    k = r['llm_name']
    llm_summary[k]['papers'] += 1
    llm_summary[k]['f1'].append(r['f1_score'] or 0)
    llm_summary[k]['std'].append(r['study_details'] or 0)
    llm_summary[k]['bmd'].append(r['bm_details'] or 0)
    llm_summary[k]['bmr'].append(r['bm_results'] or 0)
    llm_summary[k]['inf'].append(r['inferences'] or 0)
    llm_summary[k]['embed'] = r['embedding_model'] or ''
llm_summary_out = {k: (round(sum(v['f1'])/len(v['f1']),1) if v['f1'] else 0,
                       round(sum(v['std'])/len(v['std']),1) if v['std'] else 0,
                       round(sum(v['bmd'])/len(v['bmd']),1) if v['bmd'] else 0,
                       round(sum(v['bmr'])/len(v['bmr']),1) if v['bmr'] else 0,
                       round(sum(v['inf'])/len(v['inf']),1) if v['inf'] else 0,
                       v['papers'], v['embed'])
                  for k,v in llm_summary.items()}
print(f'llm_data={llm_data}')
print(f'llm_summary={dict(llm_summary_out)}')
conn.close()
PYEOF
```

Capture all printed variables. Key ones:
- `extracted`, `avg_f1`, `above70`, `top5`, `bot5` — summary stats
- `avg_bm_det`, `avg_study`, `avg_bm_res`, `avg_infer` — per-sheet averages
- `by_disease`, `by_stype`, `by_bmt` — dimension breakdowns: dict of name -> (avg_f1, count)
- `all_papers` — list of tuples: (pmid, disease, study_types[], bm_types[], f1, recall, precision, bm_det, study, bm_res, infer, bm_rows, cost)
- `llm_data` — list of tuples: (pmid, llm_name, embedding_model, std, bmd, bmr, inf, f1, run_datetime)
- `llm_summary` — dict of llm_name -> (avg_f1, avg_std, avg_bmd, avg_bmr, avg_inf, paper_count, embedding_model)

Fixed values: corpus=150, not_available=41.

---

## STEP 3 — Write the HTML file

Use the Write tool to create the file at the path from Step 1.

Generate a complete self-contained HTML document with the LIGHT theme below. Replace ALL <<PLACEHOLDERS>> with real values from Steps 1 and 2.

THEME: White background, Inter font, blue gradient hero, white cards with shadows. Matches stakeholder-deck style.

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Biomarker Extract — <<FILENAME>></title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root {
  --primary: #1a56db;
  --primary-light: #e8eefb;
  --accent: #0ea5e9;
  --success: #16a34a;
  --warning: #f59e0b;
  --danger: #dc2626;
  --purple: #7c3aed;
  --dark: #111827;
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-500: #6b7280;
  --gray-700: #374151;
  --gray-900: #111827;
  --radius: 14px;
  --shadow: 0 4px 24px rgba(0,0,0,0.06);
  --shadow-lg: 0 8px 40px rgba(0,0,0,0.10);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--gray-50); color: var(--gray-900); font-family: 'Inter', system-ui, sans-serif; font-size: 14px; line-height: 1.6; }
a { color: var(--primary); text-decoration: none; }
nav { position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,0.95); backdrop-filter: blur(12px); border-bottom: 1px solid var(--gray-200); display: flex; align-items: center; padding: 0 32px; gap: 4px; overflow-x: auto; }
.logo { font-weight: 800; font-size: 16px; color: var(--primary); margin-right: 20px; white-space: nowrap; padding: 16px 0; }
nav a { padding: 16px 12px; font-size: 13px; font-weight: 500; color: var(--gray-500); white-space: nowrap; border-bottom: 2px solid transparent; transition: all .2s; }
nav a:hover { color: var(--primary); border-bottom-color: var(--primary); }
.hero { background: linear-gradient(135deg, #1a56db 0%, #0ea5e9 50%, #7c3aed 100%); color: white; padding: 80px 32px 64px; text-align: center; position: relative; overflow: hidden; }
.hero::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 60px; background: linear-gradient(to bottom right, transparent 49%, var(--gray-50) 51%); }
.hero h1 { font-size: 44px; font-weight: 800; margin-bottom: 14px; letter-spacing: -1px; }
.hero .sub { font-size: 18px; opacity: 0.9; max-width: 680px; margin: 0 auto 16px; font-weight: 300; }
.ver { display: inline-block; background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.35); color: white; border-radius: 20px; padding: 4px 18px; font-size: 12px; font-weight: 600; margin-bottom: 32px; }
.hstats { display: flex; justify-content: center; gap: 40px; flex-wrap: wrap; margin-top: 8px; }
.hstat .num { font-size: 38px; font-weight: 800; display: block; }
.hstat .lbl { font-size: 12px; opacity: 0.8; text-transform: uppercase; letter-spacing: 1px; }
.section { max-width: 1200px; margin: 0 auto; padding: 64px 32px; }
.stitle { font-size: 30px; font-weight: 800; margin-bottom: 8px; color: var(--dark); letter-spacing: -0.5px; }
.ssub { color: var(--gray-500); margin-bottom: 32px; font-size: 15px; max-width: 760px; }
.divider { height: 1px; background: var(--gray-200); max-width: 1200px; margin: 0 auto; }
.card { background: white; border-radius: var(--radius); box-shadow: var(--shadow); padding: 28px; border: 1px solid var(--gray-200); transition: transform .2s, box-shadow .2s; }
.card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
.card h3 { font-size: 16px; font-weight: 700; margin-bottom: 10px; color: var(--dark); }
.card p { color: var(--gray-500); font-size: 13px; line-height: 1.7; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px,1fr)); gap: 20px; }
.grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px,1fr)); gap: 20px; }
.grid4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 16px; }
.tag { display: inline-block; border-radius: 20px; padding: 3px 12px; font-size: 11px; font-weight: 600; margin: 3px 2px; }
.tag-blue { background: #dbeafe; color: #1e40af; }
.tag-green { background: #dcfce7; color: #166534; }
.tag-purple { background: #ede9fe; color: #5b21b6; }
.tag-amber { background: #fef3c7; color: #92400e; }
.tag-red { background: #fee2e2; color: #991b1b; }
.tag-teal { background: #ccfbf1; color: #0f766e; }
.info { border-radius: 10px; padding: 16px 20px; font-size: 13px; margin: 16px 0; border-left: 4px solid; }
.info-blue { background: #eff6ff; border-color: var(--primary); }
.info-green { background: #f0fdf4; border-color: var(--success); }
.info-amber { background: #fffbeb; border-color: var(--warning); }
.info strong { display: block; margin-bottom: 4px; color: var(--dark); }
.arch { background: white; border-radius: var(--radius); box-shadow: var(--shadow); padding: 32px; border: 1px solid var(--gray-200); overflow-x: auto; }
.arch-row { display: flex; gap: 12px; justify-content: center; margin-bottom: 10px; flex-wrap: wrap; }
.abox { background: var(--gray-50); border: 1.5px solid var(--gray-200); border-radius: 10px; padding: 10px 16px; text-align: center; font-size: 12px; font-weight: 600; white-space: nowrap; color: var(--gray-700); }
.abox small { display: block; font-weight: 400; color: var(--gray-500); margin-top: 2px; font-size: 11px; }
.abox.at { border-color: var(--primary); color: var(--primary); background: var(--primary-light); }
.abox.ab { border-color: var(--accent); color: #0369a1; background: #e0f2fe; }
.abox.ap { border-color: var(--purple); color: var(--purple); background: #f5f3ff; }
.abox.aa { border-color: var(--warning); color: #92400e; background: #fffbeb; }
.abox.ar { border-color: var(--danger); color: var(--danger); background: #fff1f2; }
.a-arrow { text-align: center; color: var(--gray-300); font-size: 20px; margin: 4px 0; }
.a-lbl { text-align: center; font-size: 11px; color: var(--gray-500); margin-bottom: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px; }
.pipe { display: flex; flex-wrap: wrap; gap: 0; border-radius: 12px; overflow: hidden; border: 1px solid var(--gray-200); box-shadow: var(--shadow); }
.ps { flex: 1; min-width: 120px; background: white; padding: 18px 14px; border-right: 1px solid var(--gray-200); }
.ps:last-child { border-right: none; }
.ps.hi { background: var(--primary-light); }
.ps .sn { font-size: 10px; font-weight: 700; color: var(--primary); text-transform: uppercase; margin-bottom: 4px; }
.ps h4 { font-size: 12px; font-weight: 700; margin-bottom: 3px; color: var(--dark); }
.ps p { font-size: 11px; color: var(--gray-500); }
.mr { margin-bottom: 12px; }
.ml { display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 13px; color: var(--gray-700); }
.mv { font-weight: 700; }
.bar { height: 8px; background: var(--gray-100); border-radius: 4px; overflow: hidden; }
.bf { height: 100%; border-radius: 4px; }
.bg { background: linear-gradient(90deg, #16a34a, #22c55e); }
.bb { background: linear-gradient(90deg, var(--primary), var(--accent)); }
.bred { background: linear-gradient(90deg, var(--danger), #f87171); }
.spill { background: white; border: 1px solid var(--gray-200); border-radius: 12px; padding: 20px 24px; display: flex; align-items: center; gap: 16px; box-shadow: var(--shadow); }
.spill .snum { font-size: 28px; font-weight: 800; }
.spill .slbl { font-size: 11px; color: var(--gray-500); text-transform: uppercase; letter-spacing: .5px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; background: white; border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow); }
.tbl th { background: var(--dark); color: white; padding: 12px 16px; text-align: left; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
.tbl td { padding: 11px 16px; border-bottom: 1px solid var(--gray-100); vertical-align: top; }
.tbl tr:last-child td { border-bottom: none; }
.tbl tr:hover td { background: var(--primary-light); }
.roadmap-card { background: white; border-radius: var(--radius); box-shadow: var(--shadow); padding: 28px; border: 1px solid var(--gray-200); }
.roadmap-card h3 { font-size: 16px; font-weight: 700; margin-bottom: 14px; }
.roadmap-card ul { padding-left: 18px; }
.roadmap-card li { font-size: 13px; color: var(--gray-500); padding: 3px 0; line-height: 1.7; }
footer { text-align: center; padding: 36px; color: var(--gray-500); font-size: 12px; border-top: 1px solid var(--gray-200); background: white; margin-top: 48px; }
@media(max-width:768px) { .hero h1 { font-size: 28px; } .section { padding: 40px 20px; } }
</style>
</head>
<body>

<nav>
  <span class="logo">Biomarker Extract</span>
  <a href="#overview">Overview</a>
  <a href="#value">Value</a>
  <a href="#architecture">Architecture</a>
  <a href="#pipeline">Pipeline</a>
  <a href="#ai">AI Engine</a>
  <a href="#quality">Quality</a>
  <a href="#results">Results</a>
  <a href="#changes">Changes</a>
  <a href="#tech">Tech Stack</a>
  <a href="#roadmap">Roadmap</a>
  <a href="#llm-compare">LLM Compare</a>
  <a href="#papers">All Papers</a>
</nav>

<div class="hero">
  <h1>Biomarker Extract</h1>
  <p class="sub">AI-powered multi-agent system that reads oncology research papers and extracts structured biomarker data — automatically, at scale, with gold-standard verification.</p>
  <div class="ver"><<FILENAME>> &nbsp;|&nbsp; <<TODAY_DATE>> &nbsp;|&nbsp; GPT-4.1-mini</div>
  <div class="hstats">
    <div class="hstat"><span class="num">150</span><span class="lbl">Corpus Size</span></div>
    <div class="hstat"><span class="num"><<EXTRACTED>></span><span class="lbl">Extracted</span></div>
    <div class="hstat"><span class="num"><<AVG_F1>></span><span class="lbl">Avg F1 Score</span></div>
    <div class="hstat"><span class="num"><<ABOVE70>>/<<EXTRACTED>></span><span class="lbl">Above 70% Target</span></div>
    <div class="hstat"><span class="num">~$0.07</span><span class="lbl">Cost Per Paper</span></div>
    <div class="hstat"><span class="num">4</span><span class="lbl">AI Agents</span></div>
  </div>
</div>

<div class="section" id="overview">
  <div class="stitle">What Is This System?</div>
  <p class="ssub">A fully automated AI pipeline replacing weeks of expert manual biomarker curation with hours of automated processing — at a fraction of the cost.</p>
  <div class="grid3">
    <div class="card"><h3>Input: Oncology Research Papers</h3><p>Scientific PDFs from PubMed / PMC Open Access. Azure Document Intelligence parses multi-column layouts, tables, and figures into clean structured text + explicit row-column format.</p><div style="margin-top:12px"><span class="tag tag-blue">PubMed / PMC OA</span><span class="tag tag-teal">Azure DI</span></div></div>
    <div class="card" style="border-top:4px solid var(--primary)"><h3>Process: 4-Agent AI Extraction</h3><p>Four specialised AI agents extract Study Details, Biomarker Details, Statistical Results, and Clinical Inferences — each with a self-repair loop up to 5 iterations. BM_Results run in parallel (3 workers).</p><div style="margin-top:12px"><span class="tag tag-blue">GPT-4.1-mini</span><span class="tag tag-teal">RAG + FAISS</span></div></div>
    <div class="card"><h3>Output: Structured Verified Dataset</h3><p>4-sheet Excel output: Study_Details (35 fields), BM_Details (11 fields), BM_Results (29 fields), Inferences (10 fields). All scored against goldset_1k (1,000 papers).</p><div style="margin-top:12px"><span class="tag tag-purple">goldset_1k</span><span class="tag tag-green">F1 target 70%+</span></div></div>
  </div>
  <div class="info info-blue" style="margin-top:24px"><strong>Core Design Philosophy</strong>Every extraction run is a training signal. Failures improve ALL future papers generically — never paper-specific hacks. Gold standard used only post-extraction, never shown to the LLM.</div>
</div>

<div class="divider"></div>

<div class="section" id="value">
  <div class="stitle">Business Value</div>
  <p class="ssub">Manual biomarker curation costs $80–120/paper and takes 4–8 hours. This system does it for ~$0.07 in 7–10 minutes.</p>
  <div class="grid4" style="margin-bottom:28px">
    <div class="spill"><div style="font-size:28px">&#128178;</div><div><div class="snum" style="color:var(--primary)">~1000x</div><div class="slbl">Cost Reduction</div></div></div>
    <div class="spill"><div style="font-size:28px">&#9193;</div><div><div class="snum" style="color:var(--accent)">100x</div><div class="slbl">Faster</div></div></div>
    <div class="spill"><div style="font-size:28px">&#127919;</div><div><div class="snum" style="color:var(--success)"><<AVG_F1>></div><div class="slbl">Avg F1</div></div></div>
    <div class="spill"><div style="font-size:28px">&#128200;</div><div><div class="snum" style="color:var(--purple)"><<EXTRACTED>></div><div class="slbl">Papers Done</div></div></div>
  </div>
  <div class="grid4">
    <div class="card"><h3>Researchers &amp; Curators</h3><p>Get structured biomarker data without manual extraction. Hours of work done automatically.</p></div>
    <div class="card"><h3>Data Scientists</h3><p>Feed the output into downstream ML/analytics pipelines with consistent field names.</p></div>
    <div class="card"><h3>Business Teams</h3><p>Track accuracy, cost-per-paper, and scale projections with real-time DB metrics.</p></div>
    <div class="card"><h3>Tech Teams</h3><p>Maintain and extend the pipeline. Plain-text prompts — no ML expertise needed.</p></div>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="architecture">
  <div class="stitle">System Architecture</div>
  <p class="ssub">6 layers from raw PDF to verified structured output. Every layer independently replaceable.</p>
  <div class="arch">
    <div class="a-lbl">Layer 1 — Data Ingestion</div>
    <div class="arch-row">
      <div class="abox at">PubMed / PMC OA<small>Research Papers</small></div>
      <div class="abox at">download_papers.py<small>PMC + Unpaywall fallback</small></div>
      <div class="abox at">Azure Blob Storage<small>biomarker-ragcontainer</small></div>
    </div>
    <div class="a-arrow">&#8595;</div>
    <div class="a-lbl">Layer 2 — Document Processing</div>
    <div class="arch-row">
      <div class="abox ab">Azure Document Intelligence<small>PDF Layout Analysis</small></div>
      <div class="abox ab">table_parser.py<small>Row N: Col=Val format</small></div>
      <div class="abox ab">Azure Blob Storage<small>di-output container</small></div>
    </div>
    <div class="a-arrow">&#8595;</div>
    <div class="a-lbl">Layer 3 — Classification + RAG</div>
    <div class="arch-row">
      <div class="abox aa">StudyClassifier<small>Disease(17)+Type(5)+BM(3)</small></div>
      <div class="abox aa">PromptComposer<small>4-level, 42 addons</small></div>
      <div class="abox aa">FAISS Vector Index<small>top-5 context retrieval</small></div>
      <div class="abox aa">Prompt Hash<small>SHA-256 per run</small></div>
    </div>
    <div class="a-arrow">&#8595;</div>
    <div class="a-lbl">Layer 4 — AI Extraction (parallel agents, self-repair loop)</div>
    <div class="arch-row">
      <div class="abox ap">StudyDetailsAgent<small>35 fields | 1 row/paper</small></div>
      <div class="abox ap">BMDetailsAgent<small>11 fields | gap-fill if &lt;8</small></div>
      <div class="abox ap">BMResultsAgent<small>29 fields | 3 parallel workers</small></div>
      <div class="abox ap">InferencesAgent<small>10 fields | per-biomarker</small></div>
    </div>
    <div class="a-arrow">&#8595;</div>
    <div class="a-lbl">Layer 5 — Output + Verification</div>
    <div class="arch-row">
      <div class="abox at">ExcelHandler<small>biomarker-cl-out.xlsx</small></div>
      <div class="abox at">VerificationAgent<small>F1 / Recall / Precision</small></div>
      <div class="abox at">SQLite DB<small>runs_openai + prompt_hash</small></div>
      <div class="abox at">TokenTracker<small>Cost per paper</small></div>
    </div>
    <div class="a-arrow">&#8595;</div>
    <div class="a-lbl">Layer 6 — Self-Improving Training Loop</div>
    <div class="arch-row">
      <div class="abox ar">Phase 1: Extract All<small>Zero mid-batch changes</small></div>
      <div class="abox ar">Phase 2: Consolidate<small>Group failures by disease</small></div>
      <div class="abox ar">Phase 3: Re-extract<small>Below-target only</small></div>
      <div class="abox ar">Addon Updater<small>Timestamped backups</small></div>
    </div>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="pipeline">
  <div class="stitle">Processing Pipeline</div>
  <p class="ssub">Every paper follows the same 8-stage journey. Deferred batch training prevents mid-batch prompt contamination.</p>
  <div class="pipe">
    <div class="ps"><div class="sn">Stage 1</div><h4>Download</h4><p>PMC OA + Unpaywall. Skip paywalled.</p></div>
    <div class="ps"><div class="sn">Stage 2</div><h4>DI Parse</h4><p>Azure DI + table pre-processing.</p></div>
    <div class="ps"><div class="sn">Stage 3</div><h4>Classify</h4><p>Disease, study type, BM type.</p></div>
    <div class="ps hi"><div class="sn">Stage 4</div><h4>RAG Retrieve</h4><p>FAISS top-5 examples.</p></div>
    <div class="ps hi"><div class="sn">Stage 5</div><h4>4-Agent Extract</h4><p>Parallel + self-repair.</p></div>
    <div class="ps"><div class="sn">Stage 6</div><h4>Normalize</h4><p>Dedup, 8 normalizers.</p></div>
    <div class="ps"><div class="sn">Stage 7</div><h4>Verify</h4><p>F1 / Recall / Precision.</p></div>
    <div class="ps"><div class="sn">Stage 8</div><h4>Improve</h4><p>Failures update addons.</p></div>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="ai">
  <div class="stitle">AI Engine</div>
  <p class="ssub">4-level prompt hierarchy + RAG + self-repair + parallel extraction. All configurable via plain text files.</p>
  <div class="grid3">
    <div class="card" style="border-top:4px solid var(--primary)"><h3>4-Level Prompt Hierarchy</h3><p>Core rules + Disease addon (7 cancers) + Study-type addon (5 types) + BM-type addon (3 types) = 42 total addon files. Composed dynamically per paper at runtime.</p><div style="margin-top:12px"><span class="tag tag-blue">42 addon files</span></div></div>
    <div class="card" style="border-top:4px solid var(--accent)"><h3>Self-Repair Loop</h3><p>Each agent scores its own output (0-100). Score below 80 triggers repair context + re-extraction. Up to 5 iterations. ~85% pass on iteration 1.</p><div style="margin-top:12px"><span class="tag tag-teal">up to 5 iterations</span></div></div>
    <div class="card" style="border-top:4px solid var(--purple)"><h3>Parallel BM_Results</h3><p>3 concurrent ThreadPoolExecutor workers extract results per-biomarker simultaneously. Thread-safe token tracking. Results reassembled in original order.</p><div style="margin-top:12px"><span class="tag tag-purple">3 workers</span></div></div>
    <div class="card" style="border-top:4px solid var(--success)"><h3>BM_Details Gap Detection</h3><p>If fewer than 8 biomarkers found in first pass, a second-pass extraction runs automatically with a gap-fill header scanning for missed abbreviations.</p><div style="margin-top:12px"><span class="tag tag-green">second pass if &lt;8</span></div></div>
    <div class="card" style="border-top:4px solid var(--warning)"><h3>Structured Table Pre-Processing</h3><p>DI markdown tables converted to explicit Row N: Col=Val format before the LLM sees them. Both formats injected into prompt. Reduces row-miss errors.</p><div style="margin-top:12px"><span class="tag tag-amber">table_parser.py</span></div></div>
    <div class="card" style="border-top:4px solid var(--danger)"><h3>Row Count Guard</h3><p>After BM_Results: if rows below projection (N_bms x 2, or x4 for longitudinal/diagnostic), a gap-fill pass re-extracts low-count biomarkers automatically.</p><div style="margin-top:12px"><span class="tag tag-red">adaptive floor</span></div></div>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="quality">
  <div class="stitle">Quality Assurance</div>
  <p class="ssub">Honest, reproducible 3-metric scoring against goldset_1k.xlsx (1,000 expert-annotated papers). Gold data never shown to LLM during extraction.</p>
  <div class="grid3" style="margin-bottom:24px">
    <div class="card" style="text-align:center;border-top:4px solid var(--primary)"><div style="font-size:32px;font-weight:800;color:var(--primary);margin-bottom:6px">Row Recall</div><p style="font-size:12px;color:var(--gray-500);margin-bottom:10px">matched_gold_rows / total_gold_rows</p><p>What fraction of gold rows did we find?</p></div>
    <div class="card" style="text-align:center;border-top:4px solid var(--purple)"><div style="font-size:32px;font-weight:800;color:var(--purple);margin-bottom:6px">Precision</div><p style="font-size:12px;color:var(--gray-500);margin-bottom:10px">correct_fields / compared_fields</p><p>Within matched rows, how accurate are field values?</p></div>
    <div class="card" style="text-align:center;border-top:4px solid var(--success)"><div style="font-size:32px;font-weight:800;color:var(--success);margin-bottom:6px">F1 Score</div><p style="font-size:12px;color:var(--gray-500);margin-bottom:10px">2 x P x R / (P + R)</p><p>Primary metric. Target 70%+. Below triggers Phase 3.</p></div>
  </div>
  <div class="info info-green"><strong>8 Normalization Functions</strong>OS &harr; Overall Survival &nbsp;|&nbsp; log-rank &harr; Logrank Test &nbsp;|&nbsp; serum &harr; blood serum &nbsp;|&nbsp; high &harr; overexpression &nbsp;|&nbsp; NSCLC &harr; non-small cell lung cancer &nbsp;|&nbsp; Plus 5% relative numeric tolerance for rounding differences.</div>
</div>

<div class="divider"></div>

<div class="section" id="results">
  <div class="stitle">Corpus Results</div>
  <p class="ssub">150-paper corpus across 3 batches. <<EXTRACTED>> extracted, 41 not available (paywall/DNS). Updated <<TODAY_DATE>>.</p>
  <div class="grid4" style="margin-bottom:28px">
    <div class="spill"><div style="font-size:28px">&#128196;</div><div><div class="snum" style="color:var(--primary)">150</div><div class="slbl">Total Papers</div></div></div>
    <div class="spill"><div style="font-size:28px">&#9989;</div><div><div class="snum" style="color:var(--success)"><<EXTRACTED>></div><div class="slbl">Extracted</div></div></div>
    <div class="spill"><div style="font-size:28px">&#128683;</div><div><div class="snum" style="color:var(--danger)">41</div><div class="slbl">Not Available</div></div></div>
    <div class="spill"><div style="font-size:28px">&#127919;</div><div><div class="snum" style="color:var(--warning)"><<AVG_F1>></div><div class="slbl">Average F1</div></div></div>
  </div>
  <div class="grid2">
    <div>
      <h3 style="margin-bottom:14px;font-size:15px;color:var(--success)">Top 5 Papers</h3>
      <<TOP5_HTML>>
    </div>
    <div>
      <h3 style="margin-bottom:14px;font-size:15px;color:var(--danger)">Needs Improvement</h3>
      <<BOT5_HTML>>
      <div class="info info-amber" style="margin-top:14px;font-size:12px"><strong>* 34975751 — Known False Negative</strong>Not in goldset_1k. Extraction is good (116 BM_Results rows). Gold score 0% is misleading.</div>
    </div>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="changes">
  <div class="stitle">Recent Architecture Changes</div>
  <p class="ssub">All changes generalize to every paper — no paper-specific hacks ever.</p>
  <div class="grid3">
    <div class="card" style="border-left:4px solid var(--primary)"><h3>Parallel BM_Results Agents</h3><p>3 concurrent workers via ThreadPoolExecutor. ~3x throughput for papers with many biomarkers. Thread-safe token tracking. Results reassembled in original order.</p><div style="margin-top:12px"><span class="tag tag-blue">bm_results_agent.py</span></div></div>
    <div class="card" style="border-left:4px solid var(--accent)"><h3>Structured Table Pre-Processing</h3><p>table_parser.py converts DI markdown tables to explicit Row N: Col=Val format. Both versions injected into prompt. Reduces LLM row-miss errors from ambiguous pipe-delimited tables.</p><div style="margin-top:12px"><span class="tag tag-teal">table_parser.py</span></div></div>
    <div class="card" style="border-left:4px solid var(--purple)"><h3>Row Count Guard + Gap-Fill</h3><p>After BM_Results: if rows below projection, gap-fill pass runs automatically for low-count biomarkers. Floor is N_bms x 2 standard, x4 for longitudinal/diagnostic.</p><div style="margin-top:12px"><span class="tag tag-purple">main.py</span></div></div>
    <div class="card" style="border-left:4px solid var(--warning)"><h3>Prompt Hash Fingerprinting</h3><p>SHA-256 of all active prompt files (12 chars) stored per run in DB. Enables precise correlation of F1 changes to exact prompt revision that caused them.</p><div style="margin-top:12px"><span class="tag tag-amber">prompt_composer.py</span></div></div>
    <div class="card" style="border-left:4px solid var(--success)"><h3>Fuzzy Numeric Matching</h3><p>5% relative tolerance in verification: abs_diff / max_val &lt;= 0.05. Catches rounding differences like 0.84 vs 0.85 without false mismatches.</p><div style="margin-top:12px"><span class="tag tag-green">verification_agent.py</span></div></div>
    <<EXTRA_CHANGE_CARD>>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="tech">
  <div class="stitle">Technology Stack</div>
  <p class="ssub">Azure cloud services with Python AI core. All credentials in .env — never hardcoded.</p>
  <table class="tbl">
    <thead><tr><th>Component</th><th>Technology</th><th>Purpose</th></tr></thead>
    <tbody>
      <tr><td>PDF Parsing</td><td>Azure Document Intelligence</td><td>Layout model — text, tables, figures from academic PDFs</td></tr>
      <tr><td>Cloud Storage</td><td>Azure Blob Storage (2 containers)</td><td>biomarker-ragcontainer (PDFs) + di-output (JSON)</td></tr>
      <tr><td>LLM</td><td>Azure OpenAI GPT-4.1-mini</td><td>Extraction, self-repair, prompt improvement. temp=0.</td></tr>
      <tr><td>Embeddings</td><td>text-embedding-3-large</td><td>RAG vector index. 1,200-char chunks, top-5 retrieval.</td></tr>
      <tr><td>Vector Search</td><td>FAISS (local)</td><td>Cosine similarity search over training examples</td></tr>
      <tr><td>Database</td><td>SQLite (db/extraction_state.db)</td><td>Run history, F1 scores, token costs, prompt hash per run</td></tr>
      <tr><td>Output</td><td>Excel via openpyxl</td><td>4-sheet workbook, per-paper upsert, type enforcement</td></tr>
      <tr><td>Gold Standard</td><td>goldset_1k.xlsx (1,000 papers)</td><td>Read-only reference, post-extraction only, never shown to LLM</td></tr>
      <tr><td>Framework</td><td>LangChain 0.3 + Python 3.11</td><td>LLM orchestration, prompt templates, agent chaining</td></tr>
    </tbody>
  </table>
</div>

<div class="divider"></div>

<div class="section" id="roadmap">
  <div class="stitle">Roadmap</div>
  <p class="ssub">Current state, near-term priorities, and future vision.</p>
  <div class="grid3">
    <div class="roadmap-card" style="border-top:4px solid var(--success)"><h3 style="color:var(--success)">Done</h3><ul><li>4-agent extraction pipeline</li><li>Self-repair loops (up to 5 iterations)</li><li>Deferred batch training (3-phase)</li><li>4-level prompt hierarchy (42 addons)</li><li>17 disease + 5 study + 3 BM classifiers</li><li>goldset_1k scoring (1,000 papers)</li><li>8 normalization functions</li><li>Parallel BM_Results (3 workers)</li><li>Structured table pre-processing</li><li>Prompt hash per run in DB</li><li>150-paper corpus complete</li><li>CLAUDE.md onboarding + codebase cleanup</li></ul></div>
    <div class="roadmap-card" style="border-top:4px solid var(--warning)"><h3 style="color:var(--warning)">Near-Term</h3><ul><li>Target below-70% papers with addon improvements</li><li>Figure extraction (IHC, KM curves)</li><li>REST API for on-demand single paper</li><li>Live F1 monitoring dashboard</li><li>Async batch parallelisation</li><li>Multi-paper cross-corpus deduplication</li></ul></div>
    <div class="roadmap-card" style="border-top:4px solid var(--purple)"><h3 style="color:var(--purple)">Future Vision</h3><ul><li>Scale to full goldset_1k (1,000 papers)</li><li>Fine-tuned domain model</li><li>Cross-paper evidence synthesis</li><li>Automated meta-analysis generation</li><li>ClinicalTrials.gov integration</li><li>Real-time PubMed new publication alerts</li></ul></div>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="papers">
  <div class="stitle">All Papers — Detail View</div>
  <p class="ssub">Per-paper scores, disease, study type, and BM type. Sorted by processing order. Click any column header to sort.</p>

  <div class="grid3" style="margin-bottom:28px">
    <div class="card" style="border-top:4px solid var(--primary)">
      <h3>By Disease</h3>
      <<DISEASE_BARS>>
    </div>
    <div class="card" style="border-top:4px solid var(--accent)">
      <h3>By Study Type</h3>
      <<STYPE_BARS>>
    </div>
    <div class="card" style="border-top:4px solid var(--purple)">
      <h3>By Biomarker Type</h3>
      <<BMT_BARS>>
    </div>
  </div>

  <div class="grid4" style="margin-bottom:28px">
    <div class="spill"><div style="font-size:22px">&#128203;</div><div><div class="snum" style="color:var(--primary)"><<AVG_BM_DET>>%</div><div class="slbl">BM Details Avg</div></div></div>
    <div class="spill"><div style="font-size:22px">&#128196;</div><div><div class="snum" style="color:var(--accent)"><<AVG_STUDY>>%</div><div class="slbl">Study Details Avg</div></div></div>
    <div class="spill"><div style="font-size:22px">&#128202;</div><div><div class="snum" style="color:var(--danger)"><<AVG_BM_RES>>%</div><div class="slbl">BM Results Avg</div></div></div>
    <div class="spill"><div style="font-size:22px">&#128161;</div><div><div class="snum" style="color:var(--purple)"><<AVG_INFER>>%</div><div class="slbl">Inferences Avg</div></div></div>
  </div>

  <div style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <input id="tblFilter" type="text" placeholder="Filter by PMID or disease..." onkeyup="filterTable()" style="padding:8px 14px;border:1px solid var(--gray-300);border-radius:8px;font-size:13px;width:260px;outline:none">
    <span id="tblCount" style="font-size:12px;color:var(--gray-500)"></span>
  </div>

  <div style="overflow-x:auto">
  <table class="tbl" id="paperTbl">
    <thead><tr>
      <th onclick="sortTable(0)" style="cursor:pointer">PMID</th>
      <th onclick="sortTable(1)" style="cursor:pointer">Disease</th>
      <th onclick="sortTable(2)" style="cursor:pointer">Study Types</th>
      <th onclick="sortTable(3)" style="cursor:pointer">BM Type</th>
      <th onclick="sortTable(4)" style="cursor:pointer">F1 %</th>
      <th onclick="sortTable(5)" style="cursor:pointer">Recall %</th>
      <th onclick="sortTable(6)" style="cursor:pointer">Precision %</th>
      <th onclick="sortTable(7)" style="cursor:pointer">BM Det</th>
      <th onclick="sortTable(8)" style="cursor:pointer">Study</th>
      <th onclick="sortTable(9)" style="cursor:pointer">BM Res</th>
      <th onclick="sortTable(10)" style="cursor:pointer">Infer</th>
      <th onclick="sortTable(11)" style="cursor:pointer">Rows</th>
      <th onclick="sortTable(12)" style="cursor:pointer">Cost $</th>
    </tr></thead>
    <tbody id="paperTbody">
      <<ALL_PAPER_ROWS>>
    </tbody>
  </table>
  </div>
</div>

<div class="divider"></div>

<div class="section" id="llm-compare">
  <div class="stitle">LLM Comparison</div>
  <p class="ssub">Side-by-side accuracy across LLMs and embedding models on 5 focus lung cancer papers. Add a new LLM run to populate more columns.</p>

  <<LLM_SUMMARY_CARDS>>

  <div style="overflow-x:auto;margin-top:28px">
  <table class="tbl" id="llmTbl">
    <thead><tr>
      <th onclick="sortLlm(0)" style="cursor:pointer">PMID</th>
      <th onclick="sortLlm(1)" style="cursor:pointer">LLM</th>
      <th onclick="sortLlm(2)" style="cursor:pointer">Embedding</th>
      <th onclick="sortLlm(3)" style="cursor:pointer">Study Det %</th>
      <th onclick="sortLlm(4)" style="cursor:pointer">BM Det %</th>
      <th onclick="sortLlm(5)" style="cursor:pointer">BM Res %</th>
      <th onclick="sortLlm(6)" style="cursor:pointer">Inferences %</th>
      <th onclick="sortLlm(7)" style="cursor:pointer">F1 %</th>
      <th onclick="sortLlm(8)" style="cursor:pointer">Run Date</th>
    </tr></thead>
    <tbody id="llmTbody">
      <<LLM_ROWS>>
    </tbody>
  </table>
  </div>
  <div class="info info-blue" style="margin-top:16px"><strong>How to add a new LLM run</strong>Set AZURE_OPENAI_COMPLETION_DEPLOYMENT (or OPENAI_COMPLETION_MODEL) to the new model, run the 5 papers with --force, and LLM_comparison auto-populates a new row per paper. Re-run /update-deck to see results here.</div>
</div>

<footer>
  Biomarker Extract &bull; <<FILENAME>> &bull; <<TODAY_DATE>> &bull; GPT-4.1-mini &bull; goldset_1k Gold Standard (1,000 papers)
</footer>

<script>
let sortDir = {};
function sortTable(col) {
  const tb = document.getElementById('paperTbody');
  const rows = Array.from(tb.querySelectorAll('tr'));
  sortDir[col] = !sortDir[col];
  rows.sort((a,b) => {
    const av = a.cells[col].dataset.val || a.cells[col].innerText;
    const bv = b.cells[col].dataset.val || b.cells[col].innerText;
    const an = parseFloat(av), bn = parseFloat(bv);
    const cmp = isNaN(an) ? av.localeCompare(bv) : an - bn;
    return sortDir[col] ? cmp : -cmp;
  });
  rows.forEach(r => tb.appendChild(r));
  updateCount();
}
function filterTable() {
  const q = document.getElementById('tblFilter').value.toLowerCase();
  document.querySelectorAll('#paperTbody tr').forEach(r => {
    r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none';
  });
  updateCount();
}
function updateCount() {
  const vis = Array.from(document.querySelectorAll('#paperTbody tr')).filter(r=>r.style.display!='none').length;
  document.getElementById('tblCount').innerText = vis + ' papers shown';
}
updateCount();
</script>

<script>
let llmSortDir = {};
function sortLlm(col) {
  const tb = document.getElementById('llmTbody');
  const rows = Array.from(tb.querySelectorAll('tr'));
  llmSortDir[col] = !llmSortDir[col];
  rows.sort((a,b) => {
    const av = a.cells[col].dataset.val || a.cells[col].innerText;
    const bv = b.cells[col].dataset.val || b.cells[col].innerText;
    const an = parseFloat(av), bn = parseFloat(bv);
    const cmp = isNaN(an) ? av.localeCompare(bv) : an - bn;
    return llmSortDir[col] ? cmp : -cmp;
  });
  rows.forEach(r => tb.appendChild(r));
}
</script>

<script>
const secs=document.querySelectorAll('[id]');
const links=document.querySelectorAll('nav a[href^="#"]');
const ob=new IntersectionObserver(entries=>{entries.forEach(e=>{if(e.isIntersecting)links.forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+e.target.id));});},{threshold:0.2});
secs.forEach(s=>ob.observe(s));
</script>
</body>
</html>
```

For <<TOP5_HTML>> generate this pattern for each of the 5 papers:
```html
<div class="mr"><div class="ml"><span>PUBMED_ID</span><span class="mv" style="color:var(--success)">F1%</span></div><div class="bar"><div class="bf bg" style="width:F1%"></div></div></div>
```

For <<BOT5_HTML>> use same pattern but color var(--danger) and class "bred". Add * after 34975751 if it appears.

For <<EXTRA_CHANGE_CARD>>: if user provided architecture change text in ARGS, add one card with border-left:4px solid var(--gray-300). Otherwise replace with empty string.

For <<DISEASE_BARS>>, <<STYPE_BARS>>, <<BMT_BARS>>: generate bar rows using by_disease / by_stype / by_bmt dicts. Each row:
```html
<div class="mr"><div class="ml"><span>NAME (N papers)</span><span class="mv">F1%</span></div><div class="bar"><div class="bf bb" style="width:F1%"></div></div></div>
```
Use color var(--success) for F1>=70, var(--warning) for 60-70, var(--danger) for <60 in the mv span.

For <<AVG_BM_DET>>, <<AVG_STUDY>>, <<AVG_BM_RES>>, <<AVG_INFER>>: replace with the matching avg values from STEP 2.

For <<ALL_PAPER_ROWS>>: generate one <tr> per paper from all_papers list. F1 cell gets background color:
- green (#dcfce7) if F1>=70, amber (#fef3c7) if 50<=F1<70, red (#fee2e2) if F1<50.
- Study types and BM types shown as small comma-separated tags.
- Each <td> gets data-val="numeric_value" for numeric columns so sorting works correctly.
Format:
```html
<tr>
  <td>PMID</td>
  <td><span class="tag tag-blue">disease</span></td>
  <td style="font-size:11px">study_type1, study_type2</td>
  <td style="font-size:11px">bm_type1, bm_type2</td>
  <td data-val="F1" style="font-weight:700;background:COLOR">F1%</td>
  <td data-val="Recall">Recall%</td>
  <td data-val="Precision">Precision%</td>
  <td data-val="BmDet">BmDet%</td>
  <td data-val="Study">Study%</td>
  <td data-val="BmRes">BmRes%</td>
  <td data-val="Infer">Infer%</td>
  <td data-val="Rows">Rows</td>
  <td data-val="Cost">$Cost</td>
</tr>
```
Disease tag color: lung=tag-blue, liver=tag-teal, thyroid=tag-green, gastric=tag-amber, pancreatic=tag-purple, unknown=tag-red.

For <<LLM_SUMMARY_CARDS>>: generate one `.spill` card per unique LLM in llm_summary. Each card shows: LLM name (bold), embedding model (small subtitle), avg F1, papers count, avg STD/BMD/BMR/INF as small bar rows. Use a `grid3` wrapper. Example structure:
```html
<div class="grid3">
  <div class="card" style="border-top:4px solid var(--primary)">
    <h3>LLM_NAME</h3>
    <p style="font-size:11px;color:var(--gray-500);margin-bottom:12px">Embedding: EMBEDDING_MODEL &nbsp;|&nbsp; N papers</p>
    <div style="font-size:28px;font-weight:800;color:var(--primary);margin-bottom:12px">AVG_F1%</div>
    <div class="mr"><div class="ml"><span>Study Details</span><span class="mv">STD%</span></div><div class="bar"><div class="bf bb" style="width:STD%"></div></div></div>
    <div class="mr"><div class="ml"><span>BM Details</span><span class="mv">BMD%</span></div><div class="bar"><div class="bf bb" style="width:BMD%"></div></div></div>
    <div class="mr"><div class="ml"><span>BM Results</span><span class="mv">BMR%</span></div><div class="bar"><div class="bf bb" style="width:BMR%"></div></div></div>
    <div class="mr"><div class="ml"><span>Inferences</span><span class="mv">INF%</span></div><div class="bar"><div class="bf bb" style="width:INF%"></div></div></div>
  </div>
</div>
```
Use border color var(--primary) for first LLM, var(--accent) for second, var(--purple) for third, etc.

For <<LLM_ROWS>>: generate one `<tr>` per row in llm_data. F1 cell color: green (#dcfce7) if >=70, amber (#fef3c7) if 50-70, red (#fee2e2) if <50. Format:
```html
<tr>
  <td>PMID</td>
  <td><strong>LLM_NAME</strong></td>
  <td style="font-size:11px;color:var(--gray-500)">EMBEDDING</td>
  <td data-val="STD">STD%</td>
  <td data-val="BMD">BMD%</td>
  <td data-val="BMR">BMR%</td>
  <td data-val="INF">INF%</td>
  <td data-val="F1" style="font-weight:700;background:COLOR">F1%</td>
  <td style="font-size:11px;color:var(--gray-500)">RUN_DATE</td>
</tr>
```

---

## STEP 4 — Sync to user-level commands

Also copy the updated file to the user-level commands folder:
```
cp c:/dev/biomarkerv1/v5-biomarker-rag-claude/.claude/commands/update-deck.md "C:/Users/prabhu.pandian/.claude/commands/update-deck.md"
```

---

## STEP 5 — Confirm to the user

After writing the file, print:
```
Created: docs/presentations/<<FILENAME>>
Version: v<<N>> | Date: <<TODAY>> | Extracted: <<EXTRACTED>>/150 | Avg F1: <<AVG_F1>> | Above 70%: <<ABOVE70>>/<<EXTRACTED>>
Open: c:/dev/biomarkerv1/v5-biomarker-rag-claude/docs/presentations/<<FILENAME>>
```
