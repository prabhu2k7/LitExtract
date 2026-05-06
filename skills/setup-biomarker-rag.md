# Setup Biomarker RAG Extraction Pipeline

Generate a complete, production-ready Biomarker RAG Extraction Pipeline from scratch. Follow ALL steps in order. Do not skip any step.

---

## WHAT THIS SYSTEM DOES

An automated pipeline that extracts structured biomarker data from oncology research papers (PDFs):

1. PDFs uploaded to Azure Blob Storage
2. Azure Document Intelligence converts PDFs to structured JSON (text + markdown tables)
3. LLM agents extract 4 data types per paper:
   - **Study_Details** — study design, population, disease, demographics
   - **BM_Details** — biomarker names, types, biological nature
   - **BM_Results** — statistical results (p-values, effect sizes, outcomes, significance)
   - **Inferences** — author conclusions per biomarker
4. Results written to `biomarker-cl-out.xlsx` (one sheet per data type)
5. Extractions verified against a gold standard Excel file using F1/Precision/Recall scoring
6. Scores stored in SQLite DB (`db/extraction_state.db`)
7. Training loop: if F1 < 70%, analyze failures vs gold, improve prompts generically, re-extract (max 3 tries)

---

## STEP 1 — Create folder structure

```
mkdir -p agents prompts/core prompts/diseases prompts/study_types prompts/bm_types db docintel_process .rag_cache docs/presentations
```

Create these disease addon folders (each needs 3 files: study_details_addon.txt, bm_details_addon.txt, bm_results_addon.txt):
```
prompts/diseases/lung_cancer/
prompts/diseases/breast_cancer/
prompts/diseases/liver_cancer/
prompts/diseases/gastric_cancer/
prompts/diseases/thyroid_cancer/
prompts/diseases/colorectal_cancer/
prompts/diseases/pancreatic_cancer/
```

Create these study type addon folders (each needs: bm_details_addon.txt, bm_results_addon.txt, inferences_addon.txt):
```
prompts/study_types/survival_oncology/
prompts/study_types/diagnostic/
prompts/study_types/methylation/
prompts/study_types/longitudinal_clinical/
prompts/study_types/immune_infiltration/
```

Create these biomarker type addon folders (each needs: bm_details_addon.txt, bm_results_addon.txt):
```
prompts/bm_types/cellular/
prompts/bm_types/lncrna/
prompts/bm_types/composite_score/
```

---

## STEP 2 — Create `.env.example`

```
DOCUMENTINTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
DOCUMENTINTELLIGENCE_API_KEY=<your-key>
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_COMPLETION_DEPLOYMENT=gpt-4o-mini
INPUT_CONTAINER=biomarker-ragcontainer
OUTPUT_CONTAINER=di-output
LLM_PROVIDER=openai
OPENAI_COMPLETION_MODEL=gpt-4o-mini
ANTHROPIC_COMPLETION_MODEL=claude-sonnet-4-5
EMBEDDING_MODEL=text-embedding-3-large
```

---

## STEP 3 — Create `requirements.txt`

Include: openai, anthropic, azure-ai-documentintelligence, azure-storage-blob, python-dotenv, pandas, openpyxl, faiss-cpu, langchain, langchain-openai, langchain-community, tiktoken, requests, tqdm, colorama

---

## STEP 4 — Generate `config.py`

Key constants:
- `PROJECT_ROOT = Path(__file__).parent`
- `GOLD_STANDARD_FILE = PROJECT_ROOT / "goldset_1k.xlsx"` — ALWAYS this file, never change
- `OUTPUT_FILE = PROJECT_ROOT / "biomarker-cl-out.xlsx"`
- `DB_PATH = PROJECT_ROOT / "db" / "extraction_state.db"`
- `PROMPTS_DIR = PROJECT_ROOT / "prompts"`
- `RAG_CACHE_DIR = PROJECT_ROOT / ".rag_cache"`
- `INPUT_CONTAINER`, `OUTPUT_CONTAINER` — from .env
- PMID list constants: `EXPECTED_PUBMED_IDS`, `BATCH2_PUBMED_IDS` etc. as empty lists to be populated
- Load all Azure/OpenAI credentials from .env via python-dotenv

---

## STEP 5 — Generate `init_db.py`

SQLite schema for `db/extraction_state.db`:

### Table: `runs_openai`
```sql
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
)
```

### Table: `LLM_comparison`
Same columns as `runs_openai` plus `llm_name TEXT`.

Key functions:
- `init_db()` — creates tables, runs migrations via `ALTER TABLE ADD COLUMN IF NOT EXISTS`
- `upsert_extraction_log(pubmed_id, run_id, data_dict)` — upsert by pubmed_id + run_id
- `insert_benchmark_row(pubmed_id, scores_dict, model_name)` — insert F1 scores row

Cost pricing in a dict per model:
```python
_MODEL_PRICING = {
    'gpt-4o-mini':  {'input': 0.15, 'output': 0.60},
    'gpt-4.1-mini': {'input': 0.40, 'output': 1.60},
    'gpt-4.1':      {'input': 2.00, 'output': 8.00},
    'gpt-4o':       {'input': 2.50, 'output': 10.00},
    'claude-sonnet-4-5': {'input': 3.00, 'output': 15.00},
    'claude-opus-4-6':   {'input': 15.00, 'output': 75.00},
}
# ALWAYS use gpt-4o-mini pricing for gpt-4o-mini model — never Claude pricing
```

---

## STEP 6 — Generate `token_tracker.py`

Thread-safe singleton that accumulates token usage and costs across all LLM calls in a paper run.

Key design:
- Class `TokenTracker` with threading.Lock
- Methods: `add(input_tokens, output_tokens, model_name)`, `get_totals()`, `reset()`, `get_cost()`
- Pricing lookup from `_MODEL_PRICING` dict — look up by model name, fall back to gpt-4o-mini rates
- Resolve model name from env: check `LLM_PROVIDER` first, then `OPENAI_COMPLETION_MODEL` (not ANTHROPIC)
- Module-level singleton: `tracker = TokenTracker()`
- CRITICAL: cost = (input * input_price / 1_000_000) + (output * output_price / 1_000_000)

---

## STEP 7 — Generate `llm_wrapper.py`

Routes LLM calls to the correct provider based on `LLM_PROVIDER` env var.

```python
def get_llm(model=None):
    provider = os.getenv('LLM_PROVIDER', 'openai')
    if provider == 'openai':
        # Use ChatOpenAI with OPENAI_COMPLETION_MODEL
    elif provider == 'anthropic':
        # Use ChatAnthropic with ANTHROPIC_COMPLETION_MODEL
    elif provider == 'azure-openai':
        # Use AzureChatOpenAI with AZURE_OPENAI_COMPLETION_DEPLOYMENT
```

All providers return a LangChain-compatible chat model object.
Use LangChain's `ChatOpenAI`, `ChatAnthropic`, `AzureChatOpenAI`.

---

## STEP 8 — Generate `column_mappings.py`

Define field mappings for BM_Results sheet (29 fields):

```python
BM_RESULTS_COLUMNS = [
    'pubmed_id', 'biomarker_name', 'disease_name', 'outcome_name',
    'bm_outcome_association', 'outcome_direction', 'statistical_test',
    'value_type', 'r_value', 'r_ci_lower', 'r_ci_upper', 'p_value',
    'p_value_prefix', 'significance_call', 'specimen', 'specimen_timepoint',
    'methodology_technique', 'patient_stratification_criteria_results_bm',
    'case_results', 'case_ci_value', 'reference_results', 'reference_ci_value',
    'drug_therapy_combination_detail_bm', 'marker_alteration',
    'evidence_statement', 'br_application', 'biomarker_name_type_nature',
    'r_p_value', 'bm_outcome_association_direction'
]

BM_DETAILS_COLUMNS = [
    'pubmed_id', 'biomarker_name', 'biomarker_type', 'biomarker_nature',
    'biomarker_name_std', 'biomarker_name_type', 'biomarker_name_type_nature'
]

STUDY_DETAILS_COLUMNS = [
    'pubmed_id', 'study_type', 'disease_name', 'patient_count',
    'geographical_region', 'gender_distribution', 'age_range',
    'study_arm1_description', 'study_arm1_size',
    'study_arm2_description', 'study_arm2_size', 'number_of_arms',
    'follow_up_duration', 'treatment_regimen', 'inclusion_criteria',
    'exclusion_criteria', 'staging_system', 'performance_status',
    'comorbidities', 'biomarker_assessment_timing'
]

INFERENCES_COLUMNS = [
    'pubmed_id', 'biomarker_name', 'biomarker_name_type',
    'br_application', 'evidence_statement', 'bm_outcome',
    'biomarker_name_std', 'biomarker_name_type_nature'
]
```

Also define:
- `GOLDSET_FIELD_ALIASES` dict — maps goldset_1k column names to internal names (70+ entries)
- Reverse mappings for verification

---

## STEP 9 — Generate `table_parser.py`

Converts Azure DI markdown tables into explicit row-column format for LLM consumption.

Logic:
```python
def parse_markdown_tables(markdown_text: str) -> list[dict]:
    # Find all markdown tables (lines starting with |)
    # Parse header row -> column names
    # Parse each data row -> {col: val} dict
    # Return list of parsed tables

def format_tables_for_llm(tables: list[dict]) -> str:
    # Convert each table to explicit format:
    # "Table N: <context>
    #  Row 1: Col1=Val1 | Col2=Val2 | Col3=Val3
    #  Row 2: Col1=Val1 | Col2=Val2 | Col3=Val3"
    # This reduces LLM row-miss errors from ambiguous pipe-delimited tables
```

Both raw markdown AND structured format are included in prompts.

---

## STEP 10 — Generate `study_classifier.py`

Detects paper characteristics from text using keyword scoring:

```python
def detect_disease(text: str) -> str | None:
    # Score 17 disease types by keyword matches
    # diseases: lung_cancer, breast_cancer, liver_cancer, gastric_cancer,
    #   thyroid_cancer, colorectal_cancer, pancreatic_cancer, prostate_cancer,
    #   ovarian_cancer, cervical_cancer, bladder_cancer, melanoma, glioma,
    #   leukemia, lymphoma, renal_cancer, esophageal_cancer
    # Return highest-scoring disease if score > threshold, else None

def detect_study_types(text: str) -> list[str]:
    # Score 5 study types: survival_oncology, diagnostic, methylation,
    #   longitudinal_clinical, immune_infiltration
    # Return all types scoring above threshold

def detect_biomarker_types(text: str, table_text: str) -> list[str]:
    # Detect: cellular (NLR/PLR/SII/TILs), lncrna, composite_score (nomogram)
    # Return list of detected types

def detect_disease_with_confidence(text: str) -> tuple[str | None, int]:
    # Returns (disease, confidence_score)

def detect_study_types_with_confidence(text: str) -> list[tuple[str, int]]:
    # Returns [(study_type, confidence_score), ...]
```

---

## STEP 11 — Generate `prompt_composer.py`

Assembles final prompt from 4-level hierarchy:

```
Level 1: prompts/core/<agent>_core.txt          (always included)
Level 2: prompts/diseases/<disease>/<agent>_addon.txt    (if disease detected)
Level 3: prompts/study_types/<type>/<agent>_addon.txt   (if study type detected)
Level 4: prompts/bm_types/<type>/<agent>_addon.txt      (if bm type detected)
```

Key functions:
```python
def compose_prompt(agent_name: str, disease: str, study_types: list,
                   bm_types: list, document_data: dict) -> str:
    # Load core prompt
    # Append disease addon if exists
    # Append each study_type addon if exists
    # Append each bm_type addon if exists
    # Return concatenated prompt

def get_prompt_hash(disease: str, study_types: list, bm_types: list) -> str:
    # SHA-256 of all active prompt file contents (12 hex chars)
    # Used to track which prompt version produced which F1 score
```

---

## STEP 12 — Generate `document_loader.py`

Loads Azure DI output JSON from blob storage for a given PubMed ID:

```python
def load_document(pubmed_id: str) -> dict:
    # List blobs in OUTPUT_CONTAINER matching pubmed_id
    # Download each matching .layout.json file
    # Parse JSON -> extract 'content' (text) and 'tables' (markdown)
    # Return {
    #   'text_data': str,       # full text content
    #   'table_data': str,      # raw markdown tables
    #   'structured_tables': list  # parsed by table_parser
    # }
```

---

## STEP 13 — Generate `agents/base_agent.py`

Base class for all 4 extraction agents. Key design:

```python
class BaseExtractionAgent:
    def __init__(self, agent_name: str, llm, prompt_composer, token_tracker):
        self.agent_name = agent_name
        self.llm = llm
        self.max_iterations = 3  # configurable
        self.pass_threshold = 75.0

    def extract(self, pubmed_id: str, document_data: dict,
                prompt_context: dict) -> list[dict]:
        # Iteration loop (max 3 times):
        #   1. Build prompt from composer
        #   2. Call LLM
        #   3. Parse JSON response
        #   4. Run internal eval (completeness + evidence integrity)
        #   5. If score >= threshold: return result
        #   6. If failed: generate repair context, retry
        # Return best result

    def _call_llm(self, prompt: str) -> str:
        # Call LLM, track tokens, return response text

    def _parse_json_response(self, response: str) -> list[dict]:
        # Extract JSON from response (handle markdown code blocks)
        # Validate structure

    def _internal_eval(self, result: list[dict],
                       document_data: dict) -> tuple[float, str]:
        # Score: completeness (fields filled) + evidence integrity
        # Return (score_0_to_100, status_PASS_or_FAIL)

    def _generate_repair_context(self, result: list[dict],
                                  eval_feedback: str) -> str:
        # Generate hint for next iteration based on what failed
```

If `document_data` contains `_gap_fill_header` key, modify prompt to run gap-fill pass.

---

## STEP 14 — Generate `agents/study_details_agent.py`

Extracts study design fields. Single-pass (not per-biomarker).

Post-processing:
- Back-fill `geographical_region` from institution mentions if missing
- Back-fill `gender_distribution` as 'Balanced' if not specified
- Detect and fill `number_of_arms` from study arm descriptions

---

## STEP 15 — Generate `agents/bm_details_agent.py`

Extracts biomarker names, types, and biological nature.

Post-processing:
```python
def _normalize_bm_details_names(rows: list[dict]) -> list[dict]:
    # Strip trailing suffixes from biomarker names
    # Auto-fill type/nature from known defaults
    # e.g., miR-XXX -> type=RNA, nature=miRNA
    #       NLR/PLR/SII -> type=Protein, nature=Cellular Marker

def _deduplicate_rows(rows: list[dict]) -> list[dict]:
    # Remove exact duplicates (abbreviation-aware)
```

Gap detection logic:
- After first extraction, if biomarker count < 8, run second pass with `_gap_fill_header` flag
- Second pass focuses on finding missed biomarkers
- Merge results, deduplicate

---

## STEP 16 — Generate `agents/bm_results_agent.py`

Extracts statistical results. Key design: **one LLM call per biomarker** (parallel, 3 workers).

```python
def extract(self, pubmed_id: str, document_data: dict,
            biomarkers: list[str], prompt_context: dict) -> list[dict]:
    # Use ThreadPoolExecutor(max_workers=3)
    # For each biomarker: submit _extract_single_biomarker task
    # Reassemble results in original biomarker order
    # Run _normalize_extracted_rows()
    # Run _deduplicate_rows()
    # Return all rows

def _normalize_extracted_rows(rows: list[dict]) -> list[dict]:
    # Normalize effect_size_type variants
    # Normalize statistical_test abbreviations
    # Auto-fill significance_call from p_value if missing
    # Map Univariate/Multivariate Cox to standard names
```

---

## STEP 17 — Generate `agents/inferences_agent.py`

Extracts author conclusions per biomarker. Per-biomarker parallel extraction (same pattern as bm_results_agent).

Post-processing:
- Rewrite biomarker name fields to match `Name-Type-Nature` format from BM_Details
- Deduplicate inference rows

---

## STEP 18 — Generate `verification_agent.py`

Compares extracted data against gold standard. Pure rule-based (no LLM calls for scoring).

### Core logic:
```python
def verify(self, pubmed_id: str, extracted: dict,
           gold: dict) -> dict:
    # For each sheet (Study_Details, BM_Details, BM_Results, Inferences):
    #   1. Load gold rows for this pubmed_id
    #   2. Load extracted rows
    #   3. Run _group_based_compare() to match rows
    #   4. Compute F1, Recall, Precision
    # Return overall F1 = harmonic mean of sheet scores
```

### 9 normalization functions (apply before comparison):
```python
def _normalize_value_type(s: str) -> str:
    # odds ratio, hazard ratio, auc, mean, beta coefficient, etc.
    # Handle typos: "odd ratio" -> "odds ratio", "auroc" -> "auc"

def _normalize_statistical_test(s: str) -> str:
    # Univariate Analysis, Multivariate Analysis, Cox Proportional Hazards
    # Kaplan-Meier, Log-rank, Chi-square, Fisher exact, Mann-Whitney, etc.
    # Handle mojibake: Wilcoxon variants

def _normalize_specimen(s: str) -> str:
    # Serum, Plasma, Blood, Tissue, Tumor Tissue, PBMC, etc.
    # Fix: use endswith() not str.replace() for suffix stripping

def _normalize_outcome(s: str) -> str:
    # OS->overall survival, DFS->disease free survival, PFS->progression free survival
    # ORR->objective response rate, DCR->disease control rate
    # pCR->complete response, etc.

def _normalize_disease_name(s: str) -> str:
    # NSCLC->lung cancer, HCC->liver cancer, etc.

def _normalize_outcome_direction(s: str) -> str:
    # High/Elevated/Overexpressed -> high
    # Low/Reduced/Downregulated -> low

def _normalize_marker_alteration(s: str) -> str:
    # Overexpression->overexpressed, mutation/fusion/deletion->variant present

def _normalize_significance(s: str) -> str:
    # significant, non-significant, not significant

def _normalize_application(s: str) -> str:
    # Prognostic->prognosis, Diagnostic->diagnosis, Predictive->prediction
```

### Numeric comparison:
- p-value: parse prefix (<, >, =) + value separately
- Effect sizes: 5% relative tolerance (abs_diff / max_val <= 0.05)

### Biomarker alias matching:
Define `_KNOWN_BIOMARKER_ALIASES` dict mapping abbreviations to full names:
- TSH <-> Thyroid-stimulating Hormone
- CEA <-> Carcinoembryonic Antigen
- NLR <-> Neutrophil-to-Lymphocyte Ratio
- PLR <-> Platelet-to-Lymphocyte Ratio
- SII <-> Systemic Immune-Inflammation Index
- Add domain-specific aliases as needed

### Skip logic for optional fields:
```python
_SKIP_GROUP_WHEN_EXT_NULL = {
    'disease_name', 'evidence_statement', 'p_prefix',
    'patient_stratification_criteria_results_bm',
    'drug_therapy_combination_detail_bm', 'specimen_timepoint',
    'methodology_technique'
}
_SKIP_GROUP_WHEN_GOLD_NULL = {
    'outcome_direction', 'patient_stratification_criteria_results_bm',
    'value_type', 'case_results', 'case_ci_value'
}
```

---

## STEP 19 — Generate `training_loop.py`

Self-improvement loop. Runs after extraction if F1 < target.

```python
class TrainingLoop:
    def __init__(self, pipeline, verification_agent, llm,
                 target_f1=70.0, max_cycles=3):
        pass

    def run(self, pubmed_id: str, document_data: dict) -> dict:
        # Cycle loop (max 3):
        #   1. Extract with current prompts
        #   2. Verify against gold
        #   3. If F1 >= target: stop
        #   4. Analyze failures -> _pick_target_sheet()
        #   5. Generate prompt improvement via LLM
        #   6. Write improvement to addon file (NOT core)
        #   7. Re-extract
        # Return best result

    def _pick_target_sheet(self, scores: dict) -> str:
        # If BM_Results_Recall < 50% AND BM_Details_Recall < 50%:
        #   target BM_Details (upstream fix)
        # elif Field_Precision < 50%:
        #   target BM_Results with precision guard strategy
        # else:
        #   target sheet with lowest F1

    def _generate_prompt_improvement(self, sheet: str, disease: str,
                                      gold_rows: list, extracted_rows: list,
                                      failure_type: str) -> str:
        # failure_type: 'recall' or 'precision'
        # For recall failures: LLM generates rules to extract more/missing fields
        # For precision failures: LLM generates rules to filter over-extraction
        # Returns addon text to append to disease/study_type prompt file
        # CRITICAL: improvement must be generic, not paper-specific
```

---

## STEP 20 — Generate `excel_handler.py`

Read/write `biomarker-cl-out.xlsx` with upsert logic per paper.

```python
SHEETS = {
    'Study_Details': STUDY_DETAILS_COLUMNS,
    'BM_Details': BM_DETAILS_COLUMNS,
    'BM_Results': BM_RESULTS_COLUMNS,
    'Inferences': INFERENCES_COLUMNS
}

def upsert_paper(pubmed_id: str, data: dict) -> None:
    # For each sheet:
    #   1. Load existing sheet (or create empty)
    #   2. Remove all rows where pubmed_id == this paper
    #   3. Append new rows
    #   4. Enforce column types (str for text, float for numbers)
    #   5. Save back

def load_gold_standard(file_path: str) -> dict:
    # Load goldset_1k.xlsx (lowercase sheet names)
    # Apply GOLDSET_FIELD_ALIASES to normalize column names
    # Return {sheet_name: DataFrame}
```

---

## STEP 21 — Generate `main.py`

Orchestrates the full extraction pipeline:

```python
class BiomarkerExtractionPipeline:
    def __init__(self):
        # Initialize: llm, agents, excel_handler, verification_agent
        # Load FAISS index from .rag_cache if exists

    def process_paper(self, pubmed_id: str,
                      force_rerun: bool = False) -> dict:
        # 1. Load document from blob storage
        # 2. Run study_classifier -> disease, study_types, bm_types
        # 3. Update prompt_composer with classification
        # 4. Extract Study_Details
        # 5. Extract BM_Details
        # 6. Gap detection: if < 8 biomarkers, run second pass
        # 7. Extract BM_Results (parallel per biomarker)
        # 8. Extract Inferences (parallel per biomarker)
        # 9. Write to Excel
        # 10. Verify against gold standard
        # 11. Write F1 scores to DB
        # 12. Print cost summary
        # Return {pubmed_id, scores, cost}
```

---

## STEP 22 — Generate `run_paper.py`

CLI entry point:

```bash
python run_paper.py <PMID> [--force] [--verify-only]
```

- `--force`: re-extract even if already in DB
- `--verify-only`: skip extraction, just re-score against gold

---

## STEP 23 — Generate `run_with_training.py`

Training loop entry point with deferred batch mode:

```bash
python run_with_training.py --papers <PMID1> <PMID2> ... --deferred --max-cycles 3
```

### Deferred mode (`--deferred`):
```
Phase 1: Extract all papers once (no training mid-batch)
Phase 2: Group failures by disease
Phase 3: For each failure group, run training loop (improve prompts), re-extract
```

This prevents mid-batch contamination: a prompt change for paper A doesn't affect paper B already extracted.

Also supports `--batch2`, `--batch3`, etc. flags that reference PMID lists in `config.py`.

---

## STEP 24 — Generate `docintel_process/download_papers.py`

Downloads PDFs from PMC Open Access + Unpaywall fallback:

```python
# For each PMID:
# 1. PMID -> PMCID lookup via NCBI E-utilities
# 2. Try PMC OA API -> download TGZ bundle -> extract PDF
# 3. Fallback: Unpaywall API -> download PDF directly
# 4. Save to docintel_process/input/<PMID>_<N>.pdf
# 5. Log success/failure to pipeline_status.json

# CLI:
# python download_papers.py --pmid-file <file.txt> --limit <N>
```

---

## STEP 25 — Generate `docintel_process/process_docs.py`

Uploads PDFs to Azure Blob Storage, runs Azure Document Intelligence:

```python
# For each PDF in docintel_process/input/:
# 1. Skip if already in processed.json
# 2. Upload PDF to INPUT_CONTAINER blob
# 3. Submit to Azure DI (prebuilt-layout model)
# 4. Poll until complete
# 5. Save result JSON to OUTPUT_CONTAINER as <PMID>_<N>.layout.json
# 6. Mark as processed in processed.json

# CLI:
# python process_docs.py [--force]
```

---

## STEP 26 — Generate core prompt files

### `prompts/core/study_details_core.txt`
Instructions to extract study design fields. Key rules:
- Extract patient count as integer
- Standardize disease names (full name, not abbreviation)
- Extract both study arms if present
- Fill geographical_region from institution affiliation

### `prompts/core/bm_details_core.txt`
Instructions to extract biomarker catalog. Key rules:
- One row per unique biomarker
- Extract biomarker_type: RNA / Protein / Genetic / Clinical / Composite
- Extract biomarker_nature: specific biological category
- WHAT IS NOT A BIOMARKER: cell lines (A549, H460), housekeeping genes (GAPDH, beta-actin), miRNA targets-only
- Self-check: verify each extracted biomarker appears in paper as a biomarker

### `prompts/core/bm_results_core.txt`
Instructions to extract statistical results. Key rules:
- ONE ROW per unique (biomarker, outcome, statistical_test, patient_group) combination
- Extract only PRIMARY reported results — skip subgroup analyses, sensitivity analyses, and exploratory findings unless they are the main finding
- MANDATORY fields: disease_name (always fill), methodology_technique (always fill), specimen_timepoint (use 'Presentation' for baseline)
- p_value split: "p<0.05" -> p_value_prefix="<", p_value="0.05"
- application_as_per_author: 'Prognosis' for OS/DFS outcomes, 'Diagnosis' for AUC/sensitivity/specificity
- bm_outcome_association: 'Positive' if high biomarker -> better outcome, 'Negative' if high -> worse
- statistical_test vocabulary: use 'Univariate Analysis' / 'Multivariate Analysis' (not specific Cox names)
- Self-check: verify each row has a distinct p-value, verify no duplicate rows

### `prompts/core/inferences_core.txt`
Instructions to extract author conclusions. Key rules:
- One row per (biomarker, application) combination
- evidence_statement: direct quote or close paraphrase of author conclusion
- br_application: Prognosis / Diagnosis / Prediction / Monitoring

---

## STEP 27 — Generate disease addon prompt templates

For each disease folder, create 3 files with disease-specific guidance:

**`bm_results_addon.txt` template:**
```
## {DISEASE} — BM Results Specific Rules

### Common {DISEASE} Outcomes
- List primary outcomes studied in this disease (OS, DFS, RFS, etc.)

### Common {DISEASE} Biomarkers
- List typical biomarker categories studied

### {DISEASE} Staging
- Note relevant staging systems and how they appear in papers

### Terminology
- List disease-specific abbreviations and their full forms
```

**`bm_details_addon.txt` template:**
```
## {DISEASE} — Biomarker Types

### Expected Biomarker Categories
- Common RNA biomarkers in this disease
- Common protein biomarkers
- Common genetic variants

### Known Aliases
- List key abbreviation <-> full name mappings
```

**`study_details_addon.txt` template:**
```
## {DISEASE} — Study Design Notes

### Common Study Designs
- Typical cohort sizes, follow-up durations
- Common treatment regimens

### Disease-Specific Fields
- Staging system to use
- Performance status scale
```

---

## STEP 28 — Generate `run_batch_nosleep.py`

Windows sleep prevention wrapper:

```python
# Import ctypes, set EXECUTION_STATE to prevent sleep
# Forward all CLI args to run_with_training.py
# Reset EXECUTION_STATE on exit
```

---

## STEP 29 — Verify the setup

Run these checks:
```bash
# Check folder structure
ls -la agents/ prompts/core/ prompts/diseases/ db/

# Check Python imports work
python -c "from config import PROJECT_ROOT; print('config OK')"
python -c "from init_db import init_db; init_db(); print('DB OK')"
python -c "from llm_wrapper import get_llm; print('llm_wrapper OK')"

# Check .env loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('OPENAI key present:', bool(os.getenv('OPENAI_API_KEY') or os.getenv('AZURE_OPENAI_API_KEY')))"
```

---

## STEP 30 — Print setup summary

After all files are generated, print:

```
========================================
Biomarker RAG Pipeline — Setup Complete
========================================
Generated files:
  Core pipeline: main.py, run_paper.py, run_with_training.py
  Agents: 5 files in agents/
  Support: config.py, init_db.py, token_tracker.py, llm_wrapper.py
           column_mappings.py, table_parser.py, study_classifier.py
           prompt_composer.py, document_loader.py, excel_handler.py
           verification_agent.py, training_loop.py
  DI pipeline: docintel_process/download_papers.py, process_docs.py
  Prompts: core/ (4 files), diseases/ (7x3=21 files), study_types/ (5x3=15 files), bm_types/ (3x2=6 files)
  DB schema: db/extraction_state.db initialized

Next steps:
  1. Copy .env.example to .env and fill in your credentials
  2. Place your gold standard file as goldset_1k.xlsx in project root
  3. pip install -r requirements.txt
  4. Test single paper: python run_paper.py <PMID>

IMPORTANT:
  - config.py GOLD_STANDARD_FILE must always point to goldset_1k.xlsx
  - Always prefix long runs: KMP_DUPLICATE_LIB_OK=TRUE python run_with_training.py ...
  - Use --deferred for batches of 10+ papers
========================================
```
