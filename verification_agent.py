"""Rule-based verification against goldset_1k.xlsx."""
from __future__ import annotations
import re
from typing import Any

from column_mappings import SHEET_COLUMNS


# ---------- normalizers ----------

_VALUE_TYPE_MAP = {
    "hr": "hazard ratio", "or": "odds ratio", "rr": "relative risk",
    "odd ratio": "odds ratio", "hazards ratio": "hazard ratio",
    "auroc": "auc", "roc auc": "auc",
    "beta": "beta coefficient", "β": "beta coefficient",
}

_STATISTICAL_TEST_MAP = [
    (re.compile(r"uni(?:variate)?\s*cox", re.I),   "Univariate Analysis"),
    (re.compile(r"multi(?:variate)?\s*cox", re.I), "Multivariate Analysis"),
    (re.compile(r"uni(?:variate)?\s*(analysis|regression)", re.I), "Univariate Analysis"),
    (re.compile(r"multi(?:variate)?\s*(analysis|regression)", re.I), "Multivariate Analysis"),
    (re.compile(r"logistic", re.I), "Logistic Regression"),
    (re.compile(r"kaplan[- ]meier", re.I), "Kaplan-Meier"),
    (re.compile(r"log[- ]rank", re.I), "Log-rank"),
    (re.compile(r"chi[- ]square|χ2|x2", re.I), "Chi-square"),
    (re.compile(r"fisher", re.I), "Fisher exact"),
    (re.compile(r"mann[- ]whitney", re.I), "Mann-Whitney"),
    (re.compile(r"wilcoxon", re.I), "Wilcoxon"),
    (re.compile(r"t[- ]test", re.I), "Student's t-test"),
]

_SPECIMEN_MAP = {
    "serum": "serum", "plasma": "plasma", "blood": "blood",
    "tissue": "tissue", "tumor tissue": "tumor tissue",
    "tumour tissue": "tumor tissue", "pbmc": "pbmc",
    "bone marrow": "bone marrow", "csf": "csf",
    "urine": "urine", "saliva": "saliva",
}

_OUTCOME_MAP = {
    "os": "overall survival", "dfs": "disease free survival",
    "pfs": "progression free survival", "rfs": "recurrence free survival",
    "orr": "objective response rate", "dcr": "disease control rate",
    "pcr": "complete response", "cr": "complete response",
    "pr": "partial response", "sd": "stable disease",
}

_DISEASE_MAP = {
    "nsclc": "lung cancer", "sclc": "lung cancer",
    "hcc": "liver cancer", "crc": "colorectal cancer",
    "pdac": "pancreatic cancer", "rcc": "renal cancer",
    "gbm": "glioblastoma", "dlbcl": "lymphoma",
    # CIViC-style canonical names → broad indication
    "lung non-small cell carcinoma":  "lung cancer",
    "non-small cell lung cancer":     "lung cancer",
    "non small cell lung cancer":     "lung cancer",
    "lung adenocarcinoma":            "lung cancer",
    "small cell lung carcinoma":      "lung cancer",
    "estrogen-receptor positive breast cancer": "breast cancer",
    "estrogen receptor positive breast cancer": "breast cancer",
    "her2-positive breast cancer":    "breast cancer",
    "her2 positive breast cancer":    "breast cancer",
    "hr+/her2-":                       "breast cancer",
    "hepatocellular carcinoma":       "liver cancer",
    "colorectal adenocarcinoma":      "colorectal cancer",
    "colon adenocarcinoma":           "colorectal cancer",
    "colon cancer":                   "colorectal cancer",
    "rectal cancer":                  "colorectal cancer",
    "pancreatic adenocarcinoma":      "pancreatic cancer",
    "pancreatic ductal carcinoma":    "pancreatic cancer",
    "pancreatic ductal adenocarcinoma": "pancreatic cancer",
    "uveal melanoma":                 "melanoma",
    "cutaneous melanoma":             "melanoma",
    "chronic myeloid leukemia":       "cml",
    "chronic myeloid leukaemia":      "cml",
    "acute myeloid leukemia":         "aml",
    "acute myeloid leukaemia":        "aml",
    "follicular lymphoma":            "lymphoma",
    "diffuse large b-cell lymphoma":  "lymphoma",
    "b-lymphoblastic leukemia/lymphoma": "all",
    "acute lymphoblastic leukemia":   "all",
    "low grade glioma":               "glioma",
    "high grade glioma":              "glioma",
    "diffuse midline glioma":         "glioma",
    "childhood low-grade glioma":     "glioma",
    "papillary thyroid carcinoma":    "thyroid cancer",
    "esophagus squamous cell carcinoma": "esophageal cancer",
    "esophageal squamous cell carcinoma": "esophageal cancer",
    "cervical squamous cell carcinoma": "cervical cancer",
    "gastric adenocarcinoma":         "gastric cancer",
    "stomach cancer":                 "gastric cancer",
    "ovarian carcinoma":              "ovarian cancer",
    "epithelial ovarian cancer":      "ovarian cancer",
    "prostate adenocarcinoma":        "prostate cancer",
    "prostate carcinoma":             "prostate cancer",
}

_DIRECTION_MAP_HIGH = {"high", "elevated", "overexpressed", "upregulated", "increased"}
_DIRECTION_MAP_LOW  = {"low", "reduced", "downregulated", "decreased", "underexpressed"}

_APPLICATION_MAP = {
    "prognostic": "prognosis", "prognosis": "prognosis",
    "diagnostic": "diagnosis", "diagnosis": "diagnosis",
    "predictive": "prediction", "prediction": "prediction",
    "monitoring": "monitoring",
}

_ALTERATION_MAP = [
    (re.compile(r"over[\s-]?expression|overexpressed", re.I), "overexpressed"),
    (re.compile(r"under[\s-]?expression|underexpressed", re.I), "underexpressed"),
    (re.compile(r"mutation|variant|fusion|deletion|amplification", re.I), "variant present"),
]

_SIGNIFICANCE_MAP = {
    "significant": "significant", "sig": "significant",
    "non-significant": "not significant", "non significant": "not significant",
    "not significant": "not significant", "ns": "not significant",
}

_KNOWN_BIOMARKER_ALIASES = {
    "tsh": "thyroid-stimulating hormone",
    "cea": "carcinoembryonic antigen",
    "afp": "alpha-fetoprotein",
    "psa": "prostate-specific antigen",
    "nlr": "neutrophil-to-lymphocyte ratio",
    "plr": "platelet-to-lymphocyte ratio",
    "sii": "systemic immune-inflammation index",
    "lmr": "lymphocyte-to-monocyte ratio",
    "mlr": "monocyte-to-lymphocyte ratio",
    "ldh": "lactate dehydrogenase",
    "crp": "c-reactive protein",
}

# Protein / common name -> HGNC gene symbol. Generic; applies to all papers.
# When a paper uses "Cyclin D1" and CIViC gold uses "CCND1", normaliser maps
# both to "ccnd1" so they match. NEVER add paper-specific entries here.
_PROTEIN_TO_GENE = {
    "cyclin d1": "ccnd1",
    "cyclin d2": "ccnd2",
    "cyclin d3": "ccnd3",
    "cyclin e": "ccne1",
    "cyclin a": "ccna2",
    "cyclin b": "ccnb1",
    "her2": "erbb2",
    "her2/neu": "erbb2",
    "her-2": "erbb2",
    "her-2/neu": "erbb2",
    "neu": "erbb2",
    "her3": "erbb3",
    "her4": "erbb4",
    "p53": "tp53",
    "p63": "tp63",
    "p73": "tp73",
    "p16": "cdkn2a",
    "p16ink4a": "cdkn2a",
    "p14": "cdkn2a",
    "p15": "cdkn2b",
    "p21": "cdkn1a",
    "p27": "cdkn1b",
    "rb": "rb1",
    "retinoblastoma": "rb1",
    "alpha-fetoprotein": "afp",
    "carcinoembryonic antigen": "cea",
    "ki-67": "mki67",
    "ki67": "mki67",
    "androgen receptor": "ar",
    "estrogen receptor": "esr1",
    "progesterone receptor": "pgr",
    "vegf": "vegfa",
    "vegf-a": "vegfa",
    "vegf-c": "vegfc",
    "vegfr": "kdr",
    "vegfr-2": "kdr",
    "egfr-tk": "egfr",
    "egf receptor": "egfr",
    "c-myc": "myc",
    "n-myc": "mycn",
    "l-myc": "mycl",
    "c-met": "met",
    "hgf-r": "met",
    "c-kit": "kit",
    "scfr": "kit",
    "pd-l1": "cd274",
    "pdl1": "cd274",
    "pd-1": "pdcd1",
    "pdl-1": "cd274",
    "ctla4": "ctla4",
    "ctla-4": "ctla4",
    "trk": "ntrk1",
    "trka": "ntrk1",
    "trkb": "ntrk2",
    "trkc": "ntrk3",
    "ros1": "ros1",
    "alk": "alk",
    "neuregulin": "nrg1",
    "bcr-abl": "bcr::abl1",
    "bcr-abl1": "bcr::abl1",
    "bcr/abl": "bcr::abl1",
    "bcr/abl1": "bcr::abl1",
    "ph chromosome": "bcr::abl1",
    "philadelphia chromosome": "bcr::abl1",
}

# Variant suffix patterns. Strip from biomarker_name when the gene+variant
# was concatenated (CIViC style: "EGFR T790M") so it matches the extractor's
# bare gene name. Generic regex covers point mutations, fusions, indels, CNVs.
# 3-letter amino acid codes (Gly, Ala, ..., His). For variants like "Gly12Asp"
# / "p.Lys42Asp" produced by some extractors. We list explicitly to avoid
# matching arbitrary 3-letter substrings.
_AA3 = (
    "(?:Gly|Ala|Val|Leu|Ile|Pro|Phe|Trp|Met|Ser|Thr|Cys|Tyr|"
    "Asn|Gln|Asp|Glu|Lys|Arg|His)"
)

_VARIANT_SUFFIX_PATTERNS = [
    # Multi-aa variant lists: "L597P/Q/R/S" or "G469R/S/A" — strip BEFORE
    # the single point-mutation rule so the whole list goes in one shot
    re.compile(r"[\s\-]+(?:p\.)?[A-Z]\d+[A-Z*](?:/[A-Z*])+\b", re.I),
    # Single-letter point mutations: T790M, V600E, G12C, R132H, p.Lys42*
    re.compile(r"[\s\-]+(?:p\.)?[A-Z]\d+[A-Z*]\b", re.I),
    # Range / indel notation: V600_K601>E, T599_V600insT, 1596_1597insTAC,
    # p.E746_A750del — covers CIViC's HGVS-ish range mutations
    re.compile(r"[\s\-]+(?:p\.)?[A-Z]?\d+_[A-Z]?\d+(?:>\w+|(?:ins|del|dup)\w*)?\b", re.I),
    # Bare aa-position prefix(es): "KRAS G12", "KRAS G12/G13", "BRAF V600"
    re.compile(r"[\s\-]+(?:p\.)?[A-Z]\d+(?:[/, ][A-Z]?\d+)*\b", re.I),
    # 3-letter amino-acid mutations: Gly12Asp, p.Lys42Stop, Gly12Cys etc.
    re.compile(rf"[\s\-]+(?:p\.)?{_AA3}\d+(?:{_AA3}|\*|stop|fs|del|ins|dup)\b", re.I),
    # Bare aa-position prefix (e.g. paper says "KRAS-Gly12" with no end aa)
    re.compile(rf"[\s\-]+(?:p\.)?{_AA3}\d+\b", re.I),
    re.compile(r"[\s\-]+codon\s+\d+\b", re.I),
    re.compile(r"[\s\-]+amino acid\s+\d+\b", re.I),
    re.compile(r"[\s\-]+exon\s+\d+(\s+(deletion|insertion|del|ins|skip))?\b", re.I),
    re.compile(r"[\s\-]+(del|ins)\d+\b", re.I),
    re.compile(r"[\s\-]+(over|under)[- ]?expression\b", re.I),
    re.compile(r"[\s\-]+(over|under)[- ]?expressed\b", re.I),
    re.compile(r"[\s\-]+expression\b", re.I),
    re.compile(r"[\s\-]+expressed\b", re.I),
    re.compile(r"[\s\-]+amplification(s)?\b", re.I),
    re.compile(r"[\s\-]+(positive|negative)\b", re.I),
    re.compile(r"[\s\-]+(mutation|mutations|mutated|variant|variants)\b", re.I),
    re.compile(r"[\s\-]+fusion(s|-positive)?\b", re.I),
    re.compile(r"[\s\-]+deletion\b", re.I),
    re.compile(r"[\s\-]+rearrangement\b", re.I),
    re.compile(r"[\s\-]+(copy[- ]number\s+(gain|loss)|cn[- ]?gain|cn[- ]?loss)\b", re.I),
    # Loss/gain-of-function — strip BEFORE bare loss/gain rule so we don't leave "of-function"
    re.compile(r"[\s\-]+(loss|gain)[\s\-]of[\s\-]function\b", re.I),
    re.compile(r"[\s\-]+(loss|gain)\b", re.I),
    # Protein-region qualifiers — used by CIViC for kinase-domain variant clusters
    # ("ABL1 P-loop", "ABL1 non-P-loop", "BRAF kinase domain")
    re.compile(r"[\s\-]+(non[\s\-])?p[\s\-]?loop\b", re.I),
    re.compile(r"[\s\-]+kinase\s+domain\b", re.I),
    re.compile(r"[\s\-]+activation\s+loop\b", re.I),
    re.compile(r"[\s\-]+methylation\b", re.I),
    re.compile(r"[\s\-]+(itd|tkd)\b", re.I),                    # FLT3-ITD, FLT3-TKD
    re.compile(r"[\s\-]+t315i\b", re.I),
    re.compile(r"[\s\-]+(pathogenic|likely\s+pathogenic|benign|likely\s+benign|vus)\b", re.I),
    re.compile(r"[\s\-]+truncat(?:ed|ion|ing)\b", re.I),
    re.compile(r"[\s\-]+frameshift\b", re.I),
    re.compile(r"[\s\-]+nonsense\b", re.I),
    re.compile(r"[\s\-]+missense\b", re.I),
    re.compile(r"[\s\-]+splic(e|ing)(\s+(site|variant))?\b", re.I),
]


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _normalize_value_type(s: str) -> str:
    k = s.strip().lower()
    return _VALUE_TYPE_MAP.get(k, k)


def _normalize_statistical_test(s: str) -> str:
    for pat, repl in _STATISTICAL_TEST_MAP:
        if pat.search(s or ""):
            return repl
    return (s or "").strip()


def _normalize_specimen(s: str) -> str:
    k = (s or "").strip().lower()
    for suffix in (" sample", " samples", " specimen"):
        if k.endswith(suffix):
            k = k[: -len(suffix)]
    return _SPECIMEN_MAP.get(k, k)


def _normalize_outcome(s: str) -> str:
    k = (s or "").strip().lower()
    return _OUTCOME_MAP.get(k, k)


def _normalize_disease_name(s: str) -> str:
    k = (s or "").strip().lower()
    return _DISEASE_MAP.get(k, k)


def _normalize_outcome_direction(s: str) -> str:
    k = (s or "").strip().lower()
    if k in _DIRECTION_MAP_HIGH:
        return "high"
    if k in _DIRECTION_MAP_LOW:
        return "low"
    return k


def _normalize_marker_alteration(s: str) -> str:
    for pat, repl in _ALTERATION_MAP:
        if pat.search(s or ""):
            return repl
    return (s or "").strip().lower()


def _normalize_significance(s: str) -> str:
    k = (s or "").strip().lower()
    return _SIGNIFICANCE_MAP.get(k, k)


def _normalize_application(s: str) -> str:
    k = (s or "").strip().lower()
    return _APPLICATION_MAP.get(k, k)


# Druggable kinase / target genes that, when seen on the right of a fusion
# (X::Y), become the canonical reference. e.g. EML4::ALK -> alk. Special:
# BCR::ABL1 stays whole because both partners are part of the recognised
# fusion name.
_FUSION_KINASE_TARGETS = {
    "alk", "ros1", "ret", "ntrk1", "ntrk2", "ntrk3",
    "fgfr1", "fgfr2", "fgfr3", "fgfr4", "met", "egfr",
    "braf", "akt1", "pdgfra", "pdgfrb", "ros1", "kit",
    "rara",  # PML::RARA in APL — RARA is the target
    "abl1",  # BCR::ABL1 special-cased above
    "jak2",
}
_FUSION_KEEP_WHOLE: set[str] = set()


def _normalize_biomarker_name(s: str) -> str:
    """Reduce a biomarker name to its canonical gene symbol form.

    Generic transforms applied in order:
      1. Lowercase + collapse whitespace + strip parens/quotes
      2. CIViC compound profile: split on " AND " → take first part
      3. Apply protein->gene alias on the WHOLE string
      4. Strip variant suffixes (T790M, V600E, Gly12Asp, exon 19, fusion, ...)
      5. Re-check alias
      6. Fusion handling: X::Y → kinase target if recognised
      7. Biomarker abbreviation expansion (NLR -> ...)
    """
    k = (s or "").strip().lower()
    if not k:
        return k
    # Strip surrounding parens/quotes
    k = re.sub(r"^[\"'(\[]+|[\"')\]]+$", "", k).strip()
    k = re.sub(r"\s+", " ", k)

    # CIViC compound molecular profiles use " and " or " or " to join
    # multiple variants ("KRAS G12 or KRAS G13"). Take the first part.
    for sep in (" and ", " or "):
        if sep in k:
            k = k.split(sep, 1)[0].strip()
            break

    # Try alias on the WHOLE string first (catches "her2" etc.)
    # Don't return — fall through so fusion targets like "bcr::abl1" still
    # reduce to their kinase target ("abl1") in the fusion-handling block.
    if k in _PROTEIN_TO_GENE:
        k = _PROTEIN_TO_GENE[k]

    # Strip qualifier/variant suffixes (idempotent — apply repeatedly until stable)
    for _ in range(3):
        before = k
        for pat in _VARIANT_SUFFIX_PATTERNS:
            k = pat.sub("", k).strip()
        k = k.rstrip(" -:")
        if k == before:
            break

    # Re-check alias after stripping
    if k in _PROTEIN_TO_GENE:
        k = _PROTEIN_TO_GENE[k]

    # Fusion handling: if the result still contains "::" or "/" or "-" between
    # two gene-like tokens, decide which side wins.
    if "::" in k:
        if k in _FUSION_KEEP_WHOLE:
            return k
        # Split and check if right side is a recognised kinase target
        parts = [p.strip() for p in k.split("::")]
        if len(parts) == 2:
            right = parts[1]
            if right in _FUSION_KINASE_TARGETS:
                return right
            # Or left side
            if parts[0] in _FUSION_KINASE_TARGETS:
                return parts[0]
            # Default: keep whole
        return k

    # Biomarker abbreviation expansion (NLR -> ..., AFP -> ...)
    if k in _KNOWN_BIOMARKER_ALIASES:
        return _KNOWN_BIOMARKER_ALIASES[k]

    return k


def _parse_number(val: Any) -> float | None:
    if val in (None, ""):
        return None
    s = str(val).strip().replace(",", "")
    s = re.sub(r"[<>=]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _split_p_value(val: Any) -> tuple[str, str]:
    s = str(val or "").strip()
    m = re.match(r"^([<>=])\s*(.*)$", s)
    if m:
        return m.group(1), m.group(2).strip()
    return "", s


# ---------- field comparison ----------

_NUMERIC_FIELDS = {"r_value", "r_ci_lower", "r_ci_upper", "case_results", "reference_results"}
_P_VALUE_TOLERANCE = 0.05
_RELATIVE_TOL = 0.05

_NORMALIZERS = {
    "value_type":                _normalize_value_type,
    "statistical_test":          _normalize_statistical_test,
    "specimen":                  _normalize_specimen,
    "outcome_name":              _normalize_outcome,
    "disease_name":              _normalize_disease_name,
    "outcome_direction":         _normalize_outcome_direction,
    "marker_alteration":         _normalize_marker_alteration,
    "significance_call":         _normalize_significance,
    "br_application":            _normalize_application,
    "biomarker_name":            _normalize_biomarker_name,
}

_SKIP_GROUP_WHEN_EXT_NULL = {
    "disease_name", "evidence_statement", "p_prefix",
    "patient_stratification_criteria_results_bm",
    "drug_therapy_combination_detail_bm", "specimen_timepoint",
    "methodology_technique",
}

_SKIP_GROUP_WHEN_GOLD_NULL = {
    "outcome_direction", "patient_stratification_criteria_results_bm",
    "value_type", "case_results", "case_ci_value",
}


def _norm_field(field: str, value: Any) -> str:
    fn = _NORMALIZERS.get(field)
    if fn:
        return fn(_s(value))
    return _s(value).lower()


def _numbers_match(a: Any, b: Any) -> bool:
    fa = _parse_number(a)
    fb = _parse_number(b)
    if fa is None and fb is None:
        return True
    if fa is None or fb is None:
        return False
    if fa == fb == 0:
        return True
    denom = max(abs(fa), abs(fb))
    return abs(fa - fb) / denom <= _RELATIVE_TOL


def _p_value_match(gold: Any, ext: Any) -> bool:
    g_prefix, g_val = _split_p_value(gold)
    e_prefix, e_val = _split_p_value(ext)
    gn = _parse_number(g_val)
    en = _parse_number(e_val)
    if gn is None and en is None:
        return True
    if gn is None or en is None:
        return False
    if g_prefix and e_prefix and g_prefix != e_prefix:
        return False
    if gn == 0 and en == 0:
        return True
    denom = max(abs(gn), abs(en))
    return abs(gn - en) / denom <= _P_VALUE_TOLERANCE


def _field_match(field: str, gold: Any, ext: Any) -> bool:
    if field == "p_value":
        return _p_value_match(gold, ext)
    if field in _NUMERIC_FIELDS:
        return _numbers_match(gold, ext)
    return _norm_field(field, gold) == _norm_field(field, ext)


# ---------- row matching ----------

def _row_key(row: dict, fields: list[str]) -> tuple:
    return tuple(_norm_field(f, row.get(f, "")) for f in fields)


_SHEET_KEY_FIELDS = {
    "Study_Details": ["pubmed_id", "study_type", "disease_name"],
    "BM_Details":    ["biomarker_name"],
    # BM_Results: use (biomarker, br_application) instead of
    # (biomarker, outcome_name, statistical_test). CIViC gold uses outcome
    # vocabulary like "better outcome" / "drug resistance" while extractors
    # produce "Overall Survival" / "Progression-free Survival" — different
    # vocabularies. br_application (Prognosis/Prediction/Diagnosis) is the
    # axis where both sides agree.
    "BM_Results":    ["biomarker_name", "br_application"],
    "Inferences":    ["biomarker_name", "br_application"],
}


def _group_based_compare(gold_rows: list[dict],
                          ext_rows: list[dict],
                          sheet: str) -> tuple[float, float, float]:
    key_fields = _SHEET_KEY_FIELDS[sheet]
    columns = [c for c in SHEET_COLUMNS[sheet] if c != "pubmed_id"]

    if not gold_rows and not ext_rows:
        return 100.0, 100.0, 100.0
    if not gold_rows:
        return 0.0, 0.0, 0.0
    if not ext_rows:
        return 0.0, 0.0, 0.0

    gold_by_key: dict[tuple, dict] = {}
    for r in gold_rows:
        gold_by_key[_row_key(r, key_fields)] = r
    ext_by_key: dict[tuple, dict] = {}
    for r in ext_rows:
        ext_by_key[_row_key(r, key_fields)] = r

    matched = 0
    field_hits = 0
    field_total = 0

    for gk, gold in gold_by_key.items():
        ext = ext_by_key.get(gk)
        if not ext:
            continue
        matched += 1
        for f in columns:
            g = gold.get(f, "")
            e = ext.get(f, "")
            if f in _SKIP_GROUP_WHEN_EXT_NULL and _s(e) == "":
                continue
            if f in _SKIP_GROUP_WHEN_GOLD_NULL and _s(g) == "":
                continue
            if _s(g) == "" and _s(e) == "":
                continue
            field_total += 1
            if _field_match(f, g, e):
                field_hits += 1

    row_recall = (matched / len(gold_by_key) * 100) if gold_by_key else 0.0
    field_precision = (field_hits / field_total * 100) if field_total else 0.0
    f1 = (2 * row_recall * field_precision / (row_recall + field_precision)) \
        if (row_recall + field_precision) else 0.0
    return row_recall, field_precision, f1


# ---------- top-level ----------

_CANONICAL_SHEETS = ("BM_Details", "BM_Results", "Inferences")


def _canonical_biomarker_set(sheets: dict[str, list[dict]]) -> set[str]:
    """Pool unique normalized biomarker names across BM/Inference sheets."""
    out: set[str] = set()
    for sheet in _CANONICAL_SHEETS:
        for r in sheets.get(sheet) or []:
            name = _normalize_biomarker_name(r.get("biomarker_name", ""))
            if name:
                out.add(name)
    return out


class VerificationAgent:
    def verify(self, pubmed_id: str,
               extracted: dict[str, list[dict]],
               gold: dict[str, list[dict]]) -> dict[str, Any]:
        sheet_scores: dict[str, dict[str, float]] = {}
        for sheet in SHEET_COLUMNS.keys():
            g = gold.get(sheet) or []
            e = extracted.get(sheet) or []
            recall, precision, f1 = _group_based_compare(g, e, sheet)
            sheet_scores[sheet] = {
                "row_recall": round(recall, 2),
                "field_precision": round(precision, 2),
                "f1": round(f1, 2),
                "gold_count": len(g),
                "extracted_count": len(e),
            }

        f1_vals = [sheet_scores[s]["f1"] for s in SHEET_COLUMNS.keys() if sheet_scores[s]["f1"] > 0]
        overall = (sum(f1_vals) / len(f1_vals)) if f1_vals else 0.0
        recalls = [sheet_scores[s]["row_recall"] for s in SHEET_COLUMNS.keys()]
        precisions = [sheet_scores[s]["field_precision"] for s in SHEET_COLUMNS.keys()]
        avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
        avg_precision = sum(precisions) / len(precisions) if precisions else 0.0

        # Canonical biomarker capture rate — does the headline gene/variant
        # show up *anywhere* in extraction, regardless of field-level fidelity?
        gold_bms = _canonical_biomarker_set(gold)
        ext_bms = _canonical_biomarker_set(extracted)
        if gold_bms:
            captured = gold_bms & ext_bms
            canonical_recall = len(captured) / len(gold_bms) * 100
        else:
            captured = set()
            canonical_recall = 0.0

        return {
            "pubmed_id": pubmed_id,
            "F1": round(overall, 2),
            "Row_Recall": round(avg_recall, 2),
            "Field_Precision": round(avg_precision, 2),
            "Canonical_Biomarker_Recall": round(canonical_recall, 2),
            "Canonical_Gold_Set": sorted(gold_bms),
            "Canonical_Captured": sorted(captured),
            "Canonical_Missed": sorted(gold_bms - ext_bms),
            "Study_Results": sheet_scores["Study_Details"]["f1"],
            "BM_Details":    sheet_scores["BM_Details"]["f1"],
            "BM_Results":    sheet_scores["BM_Results"]["f1"],
            "Inferences":    sheet_scores["Inferences"]["f1"],
            "sheet_detail":  sheet_scores,
        }
