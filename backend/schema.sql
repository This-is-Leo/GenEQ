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

-- ------------------------------------------------------------
-- Mentor Connect
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS volunteers (
  volunteer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT NOT NULL,
  school         TEXT,
  field          TEXT,     -- e.g., "Data Analytics", "Software", "Marketing"
  email          TEXT,     -- contact email
  bio            TEXT,     -- short intro
  skills         TEXT      -- comma-separated keywords
);

CREATE TABLE IF NOT EXISTS volunteer_slots (
  slot_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  volunteer_id   INTEGER NOT NULL,
  start_utc      TEXT NOT NULL,  -- ISO8601 UTC
  end_utc        TEXT NOT NULL,  -- ISO8601 UTC
  is_booked      INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (volunteer_id) REFERENCES volunteers(volunteer_id)
);

CREATE TABLE IF NOT EXISTS bookings (
  booking_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  volunteer_id   INTEGER NOT NULL,
  slot_id        INTEGER NOT NULL,
  user_name      TEXT NOT NULL,
  user_email     TEXT NOT NULL,
  topic          TEXT,
  created_utc    TEXT NOT NULL DEFAULT (datetime('now')),
  status         TEXT NOT NULL DEFAULT 'confirmed',
  FOREIGN KEY (volunteer_id) REFERENCES volunteers(volunteer_id),
  FOREIGN KEY (slot_id) REFERENCES volunteer_slots(slot_id)
);
