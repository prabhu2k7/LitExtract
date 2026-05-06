"""Field definitions for all four output sheets + goldset aliases."""

# Source-citation columns appended to every sheet so each extracted row has
# a verbatim quote + section label pointing back to the PDF.
SOURCE_COLUMNS = ["source_excerpt", "source_section"]

BM_RESULTS_COLUMNS = [
    "pubmed_id", "biomarker_name", "disease_name", "outcome_name",
    "bm_outcome_association", "outcome_direction", "statistical_test",
    "value_type", "r_value", "r_ci_lower", "r_ci_upper", "p_value",
    "p_value_prefix", "significance_call", "specimen", "specimen_timepoint",
    "methodology_technique", "patient_stratification_criteria_results_bm",
    "case_results", "case_ci_value", "reference_results", "reference_ci_value",
    "drug_therapy_combination_detail_bm", "marker_alteration",
    "evidence_statement", "br_application", "biomarker_name_type_nature",
    "r_p_value", "bm_outcome_association_direction",
    *SOURCE_COLUMNS,
]

BM_DETAILS_COLUMNS = [
    "pubmed_id", "biomarker_name", "biomarker_type", "biomarker_nature",
    "biomarker_name_std", "biomarker_name_type", "biomarker_name_type_nature",
    *SOURCE_COLUMNS,
]

STUDY_DETAILS_COLUMNS = [
    "pubmed_id", "study_type", "disease_name", "patient_count",
    "geographical_region", "gender_distribution", "age_range",
    "study_arm1_description", "study_arm1_size",
    "study_arm2_description", "study_arm2_size", "number_of_arms",
    "follow_up_duration", "treatment_regimen", "inclusion_criteria",
    "exclusion_criteria", "staging_system", "performance_status",
    "comorbidities", "biomarker_assessment_timing",
    *SOURCE_COLUMNS,
]

INFERENCES_COLUMNS = [
    "pubmed_id", "biomarker_name", "biomarker_name_type",
    "br_application", "evidence_statement", "bm_outcome",
    "biomarker_name_std", "biomarker_name_type_nature",
    *SOURCE_COLUMNS,
]

SHEET_COLUMNS = {
    "Study_Details": STUDY_DETAILS_COLUMNS,
    "BM_Details":    BM_DETAILS_COLUMNS,
    "BM_Results":    BM_RESULTS_COLUMNS,
    "Inferences":    INFERENCES_COLUMNS,
}

# Map external goldset column names -> internal field names.
# Keys are lower-cased, whitespace-stripped for matching.
GOLDSET_FIELD_ALIASES = {
    # Study Details
    "pubmed id": "pubmed_id",
    "pmid": "pubmed_id",
    "study type": "study_type",
    "disease": "disease_name",
    "disease name": "disease_name",
    "indication": "disease_name",
    "number of patients": "patient_count",
    "patient count": "patient_count",
    "sample size": "patient_count",
    "region": "geographical_region",
    "geography": "geographical_region",
    "country": "geographical_region",
    "gender": "gender_distribution",
    "sex": "gender_distribution",
    "age": "age_range",
    "age range": "age_range",
    "arm1": "study_arm1_description",
    "arm 1": "study_arm1_description",
    "arm1 size": "study_arm1_size",
    "arm2": "study_arm2_description",
    "arm 2": "study_arm2_description",
    "arm2 size": "study_arm2_size",
    "arms": "number_of_arms",
    "number of arms": "number_of_arms",
    "follow-up": "follow_up_duration",
    "follow up": "follow_up_duration",
    "treatment": "treatment_regimen",
    "regimen": "treatment_regimen",
    "inclusion": "inclusion_criteria",
    "exclusion": "exclusion_criteria",
    "staging": "staging_system",
    "stage system": "staging_system",
    "performance status": "performance_status",
    "ecog": "performance_status",
    "comorbidity": "comorbidities",
    "assessment timing": "biomarker_assessment_timing",

    # BM Details
    "biomarker": "biomarker_name",
    "biomarker name": "biomarker_name",
    "bm": "biomarker_name",
    "type": "biomarker_type",
    "biomarker type": "biomarker_type",
    "nature": "biomarker_nature",
    "biomarker nature": "biomarker_nature",
    "standardized name": "biomarker_name_std",
    "standard name": "biomarker_name_std",
    "name type": "biomarker_name_type",
    "name-type-nature": "biomarker_name_type_nature",

    # BM Results
    "outcome": "outcome_name",
    "outcome name": "outcome_name",
    "endpoint": "outcome_name",
    "association": "bm_outcome_association",
    "bm outcome association": "bm_outcome_association",
    "direction": "outcome_direction",
    "outcome direction": "outcome_direction",
    "statistical test": "statistical_test",
    "test": "statistical_test",
    "effect size type": "value_type",
    "value type": "value_type",
    "effect size": "r_value",
    "hr": "r_value",
    "or": "r_value",
    "rr": "r_value",
    "auc": "r_value",
    "value": "r_value",
    "ci lower": "r_ci_lower",
    "95% ci lower": "r_ci_lower",
    "ci upper": "r_ci_upper",
    "95% ci upper": "r_ci_upper",
    "p value": "p_value",
    "p-value": "p_value",
    "p": "p_value",
    "p prefix": "p_value_prefix",
    "p-value prefix": "p_value_prefix",
    "significance": "significance_call",
    "significance call": "significance_call",
    "specimen": "specimen",
    "sample": "specimen",
    "timepoint": "specimen_timepoint",
    "specimen timepoint": "specimen_timepoint",
    "methodology": "methodology_technique",
    "technique": "methodology_technique",
    "assay": "methodology_technique",
    "stratification": "patient_stratification_criteria_results_bm",
    "case value": "case_results",
    "case": "case_results",
    "case ci": "case_ci_value",
    "reference value": "reference_results",
    "reference": "reference_results",
    "reference ci": "reference_ci_value",
    "drug therapy": "drug_therapy_combination_detail_bm",
    "therapy combination": "drug_therapy_combination_detail_bm",
    "marker alteration": "marker_alteration",
    "alteration": "marker_alteration",
    "evidence": "evidence_statement",
    "evidence statement": "evidence_statement",
    "application": "br_application",
    "br application": "br_application",
    "application as per author": "br_application",

    # Inferences
    "bm outcome": "bm_outcome",
}


def normalize_goldset_column(col: str) -> str:
    key = (col or "").strip().lower().replace("_", " ")
    return GOLDSET_FIELD_ALIASES.get(key, col)
