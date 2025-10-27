"""
init_db.py

Initializes a clean SQLite database for PathBuilder AI.
- Applies schema.sql
- Loads provinces, ethnicities, province/ethnicity raw exposure
- Loads jobs from NOC_Code.csv
- Loads job features from SkillsAbilitiesMerged.csv
- Loads ability-skill rubric

Run this ONCE after cleaning or updating schema.
"""

import os
import sqlite3
import pandas as pd

from backend.config import (
    DB_PATH,
    NOC_FILE,
    FEATURES_FILE,
    RUBRIC_FILE,
    NOC_JOB_ID_COL,
    NOC_TITLE_COL,
)

SCHEMA_FILE = "backend/schema.sql"
SEED_PROVINCE_ETHNICITY_FILE = "db/seed_raw.sql"

def apply_sql(conn, filename):
    """Apply all SQL commands from a .sql file to the database."""
    with open(filename, "r") as f:
        conn.executescript(f.read())

def load_jobs_and_titles(conn, noc_path):
    import pandas as pd

    df = pd.read_csv(noc_path, dtype=str, keep_default_na=False)

    # Standardize column names
    df = df.rename(columns={"NOC_CODE": "job_id", "OASIS_LABEL": "title"})

    # Clean whitespace safely on Series (use .str.strip)
    df["job_id"] = df["job_id"].fillna("").astype(str).str.strip().apply(normalize_job_id)
    df["title"]  = df["title"].fillna("").astype(str).str.strip()

    # Drop empty IDs
    df = df[df["job_id"] != ""]

    # jobs: one canonical row per job_id (keep first title)
    jobs_df = df.drop_duplicates(subset=["job_id"], keep="first")[["job_id", "title"]]

    # job_titles: keep ALL (job_id, title) pairs for UI search
    titles_df = df.drop_duplicates(subset=["job_id", "title"], keep="first")[["job_id", "title"]]

    with conn:
        conn.execute("DELETE FROM jobs")
        jobs_df.to_sql("jobs", conn, if_exists="append", index=False)

        conn.execute("DELETE FROM job_titles")
        titles_df.to_sql("job_titles", conn, if_exists="append", index=False)


def normalize_job_id(s: str) -> str:
    s = (str(s) if s is not None else "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits and len(digits) <= 4:
        return digits.zfill(4)  # "1" -> "0001"
    return s

def load_job_features(conn, features_path):
    import pandas as pd, json

    # --- read features wide CSV
    raw = pd.read_csv(features_path, dtype=str, keep_default_na=False)

    # standardize column names
    if "NOC_CODE" not in raw.columns:
        raise RuntimeError("SkillsAbilitiesMerged.csv must contain NOC_CODE column")
    raw.rename(columns={"NOC_CODE": "job_id"}, inplace=True)

    # normalize ids
    raw["job_id"] = raw["job_id"].apply(normalize_job_id)

    # drop empty ids
    raw = raw[raw["job_id"] != ""]

    # ensure numeric features actually numeric; coerce invalid to NaN then fill 0
    non_id_cols = [c for c in raw.columns if c not in {"job_id", "OASIS_LABEL"}]
    for c in non_id_cols:
        if c != "job_id":
            raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0.0)

    # collapse to ONE row per job_id by averaging duplicates
    agg = raw.drop(columns=["OASIS_LABEL"], errors="ignore").groupby("job_id", as_index=False).mean()

    # keep only job_ids that exist in jobs (prevents FK errors)
    jobs = pd.read_sql_query("SELECT job_id FROM jobs", conn)
    keep = set(jobs["job_id"].astype(str))
    agg = agg[agg["job_id"].astype(str).isin(keep)]

    # serialize each row’s features (excluding job_id) to JSON
    feat_cols = [c for c in agg.columns if c != "job_id"]
    features_json = pd.DataFrame({
        "job_id": agg["job_id"],
        "features_json": agg[feat_cols].apply(lambda r: r.to_json(), axis=1)
    })

    with conn:
        conn.execute("DELETE FROM job_features_raw")
        features_json.to_sql("job_features_raw", conn, if_exists="append", index=False)



def main():
    # ----------------------------------------------------
    # Step 1 — Reset DB
    # ----------------------------------------------------
    if os.path.exists(DB_PATH):
        print(f"Removing old database: {DB_PATH}")
        os.remove(DB_PATH)

    print(f"Creating new database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    # ----------------------------------------------------
    # Step 2 — Apply schema
    # ----------------------------------------------------
    print("Applying schema.sql...")
    apply_sql(conn, SCHEMA_FILE)

    # ----------------------------------------------------
    # Step 3 — Seed provinces and ethnicities + raw risks
    # ----------------------------------------------------
    print("Seeding province + ethnicity raw data...")
    apply_sql(conn, SEED_PROVINCE_ETHNICITY_FILE)

    # ----------------------------------------------------
    # Step 4 — Load NOC job titles
    # ----------------------------------------------------
    print(f"Loading jobs from {NOC_FILE}...")
    load_jobs_and_titles(conn, NOC_FILE)

    # ----------------------------------------------------
    # Step 5 — Load job features
    # ----------------------------------------------------
    print(f"Loading job features from {FEATURES_FILE}...")
    load_job_features(conn, FEATURES_FILE)

    # ----------------------------------------------------
    # Step 6 — Load ability-skill rubric
    # ----------------------------------------------------
    print(f"Loading ability-skill rubric from {RUBRIC_FILE}...")
    rub_df = pd.read_csv(RUBRIC_FILE)
    rub_df.rename(
        columns={
            "Name": "name",
            "Substitution_Index": "substitution_index",
            "Complementarity_Index": "complementarity_index",
        },
        inplace=True
    )
    rub_df[["name", "substitution_index", "complementarity_index"]].to_sql(
        "ability_skill_rubric_raw", conn, if_exists="append", index=False
    )

    print("Database initialization complete.")
    conn.close()


if __name__ == "__main__":
    main()
