"""Central configuration. Loaded by every module."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.resolve()

# ---- Paths (do NOT change GOLD_STANDARD_FILE name) ----
GOLD_STANDARD_FILE = PROJECT_ROOT / "goldset_1k.xlsx"
OUTPUT_FILE        = PROJECT_ROOT / "biomarker-cl-out.xlsx"
DB_PATH            = PROJECT_ROOT / "db" / "extraction_state.db"
PROMPTS_DIR        = PROJECT_ROOT / "prompts"
RAG_CACHE_DIR      = PROJECT_ROOT / ".rag_cache"
DOCINTEL_INPUT_DIR = PROJECT_ROOT / "docintel_process" / "input"

for _p in (DB_PATH.parent, RAG_CACHE_DIR, DOCINTEL_INPUT_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ---- Azure Document Intelligence ----
DOCUMENTINTELLIGENCE_ENDPOINT = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT", "")
DOCUMENTINTELLIGENCE_API_KEY  = os.getenv("DOCUMENTINTELLIGENCE_API_KEY", "")

# ---- Azure Blob Storage ----
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
INPUT_CONTAINER  = os.getenv("INPUT_CONTAINER",  "biomarker-ragcontainer")
OUTPUT_CONTAINER = os.getenv("OUTPUT_CONTAINER", "di-output")

# ---- LLM ----
LLM_PROVIDER             = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY", "")
OPENAI_COMPLETION_MODEL  = os.getenv("OPENAI_COMPLETION_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY        = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_COMPLETION_MODEL = os.getenv("ANTHROPIC_COMPLETION_MODEL", "claude-sonnet-4-5")
AZURE_OPENAI_ENDPOINT     = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY      = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION  = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
AZURE_OPENAI_COMPLETION_DEPLOYMENT = os.getenv("AZURE_OPENAI_COMPLETION_DEPLOYMENT", "gpt-4o-mini")

# ---- Embeddings ----
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
USE_EMBEDDINGS     = os.getenv("USE_EMBEDDINGS", "true").lower() == "true"

# ---- Pipeline behaviour ----
TRAINING_MODE = os.getenv("TRAINING_MODE", "true").lower() == "true"
TARGET_F1     = 70.0
MAX_TRAINING_CYCLES = 3
BM_RESULTS_PARALLEL_WORKERS = 3

# ---- PMID batches (populate as you onboard papers) ----
EXPECTED_PUBMED_IDS = []
BATCH2_PUBMED_IDS   = []
BATCH3_PUBMED_IDS   = []
BATCH4_PUBMED_IDS   = []


def active_model_name() -> str:
    """Return the currently configured completion model name."""
    if LLM_PROVIDER == "openai":
        return OPENAI_COMPLETION_MODEL
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_COMPLETION_MODEL
    if LLM_PROVIDER == "azure-openai":
        return AZURE_OPENAI_COMPLETION_DEPLOYMENT
    return OPENAI_COMPLETION_MODEL
