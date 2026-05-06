"""Detect disease / study type / biomarker type via keyword scoring."""
from __future__ import annotations
import re

_DISEASE_KEYWORDS: dict[str, list[str]] = {
    "lung_cancer": ["lung cancer", "nsclc", "small cell lung", "sclc",
                    "lung adenocarcinoma", "pulmonary carcinoma"],
    "breast_cancer": ["breast cancer", "mammary carcinoma", "her2",
                      "triple-negative breast", "tnbc", "dcis"],
    "liver_cancer": ["hepatocellular carcinoma", "hcc", "liver cancer",
                     "cholangiocarcinoma", "hepatic carcinoma"],
    "gastric_cancer": ["gastric cancer", "stomach cancer", "gastric adenocarcinoma"],
    "thyroid_cancer": ["thyroid cancer", "papillary thyroid", "ptc",
                       "follicular thyroid", "medullary thyroid"],
    "colorectal_cancer": ["colorectal cancer", "crc", "colon cancer",
                          "rectal cancer", "colon adenocarcinoma"],
    "pancreatic_cancer": ["pancreatic cancer", "pdac", "pancreatic ductal"],
    "prostate_cancer": ["prostate cancer", "prostatic carcinoma", "castration-resistant"],
    "ovarian_cancer": ["ovarian cancer", "epithelial ovarian"],
    "cervical_cancer": ["cervical cancer", "cervical carcinoma"],
    "bladder_cancer": ["bladder cancer", "urothelial carcinoma"],
    "melanoma": ["melanoma", "cutaneous melanoma"],
    "glioma": ["glioma", "glioblastoma", "gbm", "astrocytoma"],
    "leukemia": ["leukemia", "aml", "cll", "all", "cml"],
    "lymphoma": ["lymphoma", "dlbcl", "hodgkin", "non-hodgkin"],
    "renal_cancer": ["renal cell carcinoma", "rcc", "kidney cancer"],
    "esophageal_cancer": ["esophageal cancer", "esophageal carcinoma",
                          "esophageal squamous"],
}

_STUDY_TYPE_KEYWORDS: dict[str, list[str]] = {
    "survival_oncology": ["overall survival", "progression-free survival",
                          "disease-free survival", "recurrence-free",
                          "hazard ratio", "kaplan-meier", "cox regression"],
    "diagnostic": ["sensitivity", "specificity", "roc curve", "auc",
                   "diagnostic accuracy", "ppv", "npv"],
    "methylation": ["methylation", "cpg island", "5-methylcytosine",
                    "dna methylation", "hypermethylation", "hypomethylation"],
    "longitudinal_clinical": ["longitudinal", "follow-up", "cohort study",
                              "prospective cohort", "baseline to"],
    "immune_infiltration": ["tumor-infiltrating", "til", "immune infiltrat",
                            "cd8", "cd4", "treg", "macrophage infiltrat"],
}

_BM_TYPE_KEYWORDS: dict[str, list[str]] = {
    "cellular": ["nlr", "plr", "sii", "tils", "neutrophil-to-lymphocyte",
                 "platelet-to-lymphocyte", "systemic immune-inflammation"],
    "lncrna": ["lncrna", "long non-coding rna", "long noncoding rna"],
    "composite_score": ["nomogram", "composite score", "risk score",
                        "prognostic index", "scoring system"],
}

_DISEASE_THRESHOLD = 1
_STUDY_THRESHOLD = 1
_BM_THRESHOLD = 1


def _score(text: str, keywords: list[str]) -> int:
    t = text.lower()
    return sum(1 for kw in keywords if kw in t)


def detect_disease(text: str) -> str | None:
    scores = {d: _score(text, kws) for d, kws in _DISEASE_KEYWORDS.items()}
    best = max(scores.items(), key=lambda kv: kv[1]) if scores else (None, 0)
    return best[0] if best[1] >= _DISEASE_THRESHOLD else None


def detect_disease_with_confidence(text: str) -> tuple[str | None, int]:
    scores = {d: _score(text, kws) for d, kws in _DISEASE_KEYWORDS.items()}
    sorted_s = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not sorted_s or sorted_s[0][1] < _DISEASE_THRESHOLD:
        return None, 0
    return sorted_s[0]


def detect_study_types(text: str) -> list[str]:
    return [s for s, kws in _STUDY_TYPE_KEYWORDS.items()
            if _score(text, kws) >= _STUDY_THRESHOLD]


def detect_study_types_with_confidence(text: str) -> list[tuple[str, int]]:
    out = [(s, _score(text, kws)) for s, kws in _STUDY_TYPE_KEYWORDS.items()]
    return [(s, n) for s, n in out if n >= _STUDY_THRESHOLD]


def detect_biomarker_types(text: str, table_text: str = "") -> list[str]:
    combined = f"{text}\n{table_text}"
    return [bt for bt, kws in _BM_TYPE_KEYWORDS.items()
            if _score(combined, kws) >= _BM_THRESHOLD]


def classify(text: str, table_text: str = "") -> dict:
    disease, conf = detect_disease_with_confidence(text)
    level = "HIGH" if conf >= 5 else "MEDIUM" if conf >= 2 else "LOW"
    return {
        "disease": disease,
        "disease_confidence": conf,
        "confidence_level": level,
        "study_types": detect_study_types(text),
        "bm_types": detect_biomarker_types(text, table_text),
    }
