PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- Provinces in Canada (user geography input)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provinces (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

-- Raw province AI exposure values copied exactly from graphs
CREATE TABLE IF NOT EXISTS province_risk_raw (
    province_code TEXT PRIMARY KEY,
    exposure_value REAL NOT NULL,
    FOREIGN KEY (province_code) REFERENCES provinces(code)
);

-- Normalized province risk (calculated from raw)
CREATE TABLE IF NOT EXISTS province_risk (
    province_code TEXT PRIMARY KEY,
    risk REAL NOT NULL CHECK (risk >= 0 AND risk <= 1),
    FOREIGN KEY (province_code) REFERENCES provinces(code)
);

-- ------------------------------------------------------------
-- Ethnic group selection based on StatsCanada visible minority groups
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ethnicities (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

-- Raw ethnicity exposure data from graph
CREATE TABLE IF NOT EXISTS ethnicity_risk_raw (
    ethnicity_code TEXT PRIMARY KEY,
    exposure_value REAL NOT NULL,
    FOREIGN KEY (ethnicity_code) REFERENCES ethnicities(code)
);

-- Normalized ethnicity risk (calculated)
CREATE TABLE IF NOT EXISTS ethnicity_risk (
    ethnicity_code TEXT PRIMARY KEY,
    risk REAL NOT NULL CHECK (risk >= 0 AND risk <= 1),
    FOREIGN KEY (ethnicity_code) REFERENCES ethnicities(code)
);

-- ------------------------------------------------------------
-- Job tables (from NOC file)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,          -- NOC_CODE
    title TEXT NOT NULL               -- OASIS_LABEL
);

-- ------------------------------------------------------------
-- All (job_id, title) pairs for UI search (many titles per NOC)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_titles (
    job_id TEXT NOT NULL,
    title  TEXT NOT NULL,
    PRIMARY KEY (job_id, title),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);


-- ------------------------------------------------------------
-- Raw features for each job (SkillsAbilitiesMerged.csv)
-- Store as JSON per job
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_features_raw (
    job_id TEXT PRIMARY KEY,
    features_json TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

-- ------------------------------------------------------------
-- Rubric for substitution/complementarity indexes
-- AbilitySkillRubric.csv
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ability_skill_rubric_raw (
    name TEXT PRIMARY KEY,
    substitution_index REAL NOT NULL,
    complementarity_index REAL NOT NULL
);

-- ------------------------------------------------------------
-- Job PCS profile table
-- Stores Physical + Social + Creative score share for each job
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_profile (
    job_id TEXT PRIMARY KEY,
    pcs_share REAL NOT NULL, -- between 0 and 1
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

-- ------------------------------------------------------------
-- Final job risk table
-- This will be recalculated at startup
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_risk (
    job_id TEXT PRIMARY KEY,
    risk REAL NOT NULL CHECK (risk >= 0 AND risk <= 1),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
