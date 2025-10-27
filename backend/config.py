"""
Keeps project paths consistent and organized
"""

# Database path
DB_PATH = "db/risk.db"

# Data files used during initialization
NOC_FILE = "data/NOC_Code.csv"  # job ID + job titles
FEATURES_FILE = "data/SkillsAbilitiesMerged.csv"  # job skills+abilities by job_id
RUBRIC_FILE = "data/AbilitySkillRubric.csv"  # substitution/complementary index

# Column mapping for NOC file
NOC_JOB_ID_COL = "NOC_CODE"
NOC_TITLE_COL = "OASIS_LABEL"

# PCSs will read categories based on your own keyword rules (already inside compute.py)
CATEGORY_MAP_ENABLED = True

# Normalization behavior
NORMALIZE_JOB_RISK = True
