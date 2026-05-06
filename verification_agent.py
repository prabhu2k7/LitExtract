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


def _normalize_biomarker_name(s: str) -> str:
    k = (s or "").strip().lower()
    k = re.sub(r"\s+", " ", k)
    k = _KNOWN_BIOMARKER_ALIASES.get(k, k)
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
    "BM_Results":    ["biomarker_name", "outcome_name", "statistical_test"],
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

        return {
            "pubmed_id": pubmed_id,
            "F1": round(overall, 2),
            "Row_Recall": round(avg_recall, 2),
            "Field_Precision": round(avg_precision, 2),
            "Study_Results": sheet_scores["Study_Details"]["f1"],
            "BM_Details":    sheet_scores["BM_Details"]["f1"],
            "BM_Results":    sheet_scores["BM_Results"]["f1"],
            "Inferences":    sheet_scores["Inferences"]["f1"],
            "sheet_detail":  sheet_scores,
        }
