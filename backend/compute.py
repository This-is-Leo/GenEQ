"""
compute.py (clean)

What this module does:
1) normalize_dimension()
   - Min–max normalize raw exposure values (province/ethnicity) into 0..1 risk.

2) compute_job_risk(conn)
   - Reads job features (SkillsAbilitiesMerged.csv) from job_features_raw.
   - Reads rubric (AbilitySkillRubric.csv) from ability_skill_rubric_raw.
   - For each job:
       a) Sum Substitution and Complementarity totals across features:
          sub_raw += (feature_level_scaled * substitution_index_scaled)
          cmp_raw += (feature_level_scaled * complementarity_index_scaled)
          where 'scaled' divides by 5.0 (CSV is 0..5 scale and rubric is 1..5).
       b) Determine category of each feature using your PCS mapping.
          - PHYSICAL/CREATIVE/SOCIAL add to the PCS numerator and denominator.
          - ROUTINE adds to the denominator only.
          - OTHER is ignored for PCS (neither numerator nor denominator).
       c) pcs_share = (PHYSICAL + CREATIVE + SOCIAL mass) / (PHYSICAL + CREATIVE + SOCIAL + ROUTINE mass)
       d) Base job risk = sub_raw / (sub_raw + cmp_raw)
       e) Apply PCS penalty: job_risk = base_job_risk * (1 - pcs_share)
   - Normalize all job_risk values globally to [0,1].
   - Write:
       - job_profile(job_id, pcs_share)
       - job_risk(job_id, risk)
"""

from __future__ import annotations
import json
import re
import sqlite3
from typing import Dict, Tuple

import numpy as np
import pandas as pd

# -----------------------------
# Helper: key normalization
# -----------------------------
_PUNCT_RE = re.compile(r"[^\w\s]+")

def norm_key(s: str) -> str:
    """Lowercase, strip, remove punctuation, collapse whitespace."""
    s = (s or "").strip().lower()
    s = _PUNCT_RE.sub(" ", s)
    return " ".join(s.split())

# -----------------------------
# PCS category mapping
# -----------------------------
CATEGORY_MAP = [
    # ROUTINE
    (
        re.compile(
            r"\b("
            r"Operation Monitoring of Machinery and Equipment|Quality Control Testing|"
            r"Monitoring|Categorization Flexibility|Numeracy|Information Ordering|"
            r"Pattern Identification|Pattern Organization Speed"
            r")\b",
            re.I,
        ),
        "ROUTINE",
    ),

    # PHYSICAL
    (
        re.compile(
            r"\b("
            r"Repairing|Setting up|Memorizing|Multitasking|Perceptual Speed|"
            r"Selective Attention|Spatial Orientation|Spatial Visualization|Verbal Ability|"
            r"Body Flexibility|Dynamic Strength|Explosive Strength|Gross Body Coordination|"
            r"Gross Body Equilibrium|Multi-Limb Coordination|Stamina|Static Strength|"
            r"Trunk Strength|Arm-Hand Steadiness|Control of Settings|Finger Dexterity|"
            r"Manual Dexterity|Multi-Signal Response|Rate Control|Reaction Time|"
            r"Speed of Limb Movement|Finger-Hand-Wrist Motion|Auditory Attention|"
            r"Depth Perception|Far Vision|Glare Tolerance|Hearing Sensitivity|Near Vision|"
            r"Night Vision|Peripheral Vision|Speech Clarity|Speech Recognition|"
            r"Sound Localization|Colour Perception"
            r")\b",
            re.I,
        ),
        "PHYSICAL",
    ),

    # CREATIVE
    (re.compile(r"\b(Fluency of Ideas|Product Design)\b", re.I), "CREATIVE"),

    # SOCIAL
    (
        re.compile(
            r"\b("
            r"Oral Communication: Active Listening|Oral Communication: Oral Comprehension|"
            r"Oral Communication: Oral Expression|Coordinating|Instructing|Negotiating|"
            r"Persuading|Social Perceptiveness"
            r")\b",
            re.I,
        ),
        "SOCIAL",
    ),
]

PCS_SET = {"PHYSICAL", "CREATIVE", "SOCIAL"}

def category_for(feature_name: str) -> str:
    """Return one of ROUTINE/PHYSICAL/CREATIVE/SOCIAL/OTHER (default OTHER)."""
    for rx, cat in CATEGORY_MAP:
        if rx.search(feature_name or ""):
            return cat
    return "OTHER"  # default (does not affect PCS)

# ============================================================
# 1) Normalize dimensions (province/ethnicity) from *_raw -> normalized
# ============================================================
def normalize_dimension(
    conn: sqlite3.Connection,
    table_raw: str,
    key_col: str,
    table_out: str,
    out_key_col: str,
    out_val_col: str,
) -> None:
    """
    Min–max normalize exposure_value in table_raw (higher = riskier) into 0..1,
    then write to table_out(out_key_col, out_val_col).
    """
    raw = pd.read_sql_query(f"SELECT {key_col} AS k, exposure_value AS v FROM {table_raw}", conn)
    if raw.empty:
        conn.execute(f"DELETE FROM {table_out}")
        conn.commit()
        return

    vmin, vmax = raw["v"].min(), raw["v"].max()
    if vmax == vmin:
        raw["risk"] = 0.5  # degenerate case: everything identical
    else:
        raw["risk"] = (raw["v"] - vmin) / (vmax - vmin)

    # write normalized table
    out = raw[["k", "risk"]].rename(columns={"k": out_key_col, "risk": out_val_col})
    conn.execute(f"DELETE FROM {table_out}")
    out.to_sql(table_out, conn, if_exists="append", index=False)
    conn.commit()

# ============================================================
# 2) Compute job_risk and job_profile
# ============================================================
def compute_job_risk(conn: sqlite3.Connection) -> None:
    """
    Compute job risk from Substitution vs Complementarity with PCS penalty.
    Writes:
      - job_profile(job_id, pcs_share)
      - job_risk(job_id, risk)
    """
    # Load job features (wide columns stored as JSON)
    jf = pd.read_sql_query("SELECT job_id, features_json FROM job_features_raw", conn)
    if jf.empty:
        conn.execute("DELETE FROM job_profile")
        conn.execute("DELETE FROM job_risk")
        conn.commit()
        return

    # Load rubric: Name, Substitution_Index, Complementarity_Index
    rb = pd.read_sql_query(
        "SELECT name, substitution_index, complementarity_index FROM ability_skill_rubric_raw",
        conn,
    )
    if rb.empty:
        conn.execute("DELETE FROM job_profile")
        conn.execute("DELETE FROM job_risk")
        conn.commit()
        return

    # Build rubric map using normalized keys
    rubric: Dict[str, Tuple[float, float]] = {}
    for _, row in rb.iterrows():
        key = norm_key(str(row["name"]))
        s = float(row["substitution_index"]) if pd.notna(row["substitution_index"]) else 0.0
        c = float(row["complementarity_index"]) if pd.notna(row["complementarity_index"]) else 0.0
        # Scale rubric 1..5 down to 0..1
        rubric[key] = (max(0.0, min(1.0, s / 5.0)), max(0.0, min(1.0, c / 5.0)))

    # Process each job
    rows = []
    for _, r in jf.iterrows():
        job_id = r["job_id"]
        try:
            feats = json.loads(r["features_json"])
        except Exception:
            feats = {}

        sub_raw = 0.0
        cmp_raw = 0.0

        # For PCS share computation
        pcs_mass = 0.0                    # PHYSICAL + CREATIVE + SOCIAL mass
        pcs_den  = 0.0                    # PHYSICAL + CREATIVE + SOCIAL + ROUTINE mass

        for hdr, raw_val in feats.items():
            # numeric feature level in CSV expected to be 0..5 (cap to 0..5)
            try:
                val = float(raw_val)
            except Exception:
                continue
            val = max(0.0, min(5.0, val))
            val_scaled = val / 5.0        # to 0..1

            # rubric match
            k = norm_key(str(hdr))
            if k not in rubric:
                # missing names default to OTHER; they still contribute to job risk if val > 0
                sub_idx, cmp_idx = 0.0, 0.0
            else:
                sub_idx, cmp_idx = rubric[k]

            # accumulate substitution/complementarity
            sub_raw += val_scaled * sub_idx
            cmp_raw += val_scaled * cmp_idx

            # category for PCS
            cat = category_for(str(hdr))
            if cat in PCS_SET:
                pcs_mass += val_scaled
                pcs_den  += val_scaled
            elif cat == "ROUTINE":
                pcs_den  += val_scaled
            # OTHER: does not affect pcs_mass nor pcs_den

        # Base job risk (safe against division by zero)
        base = sub_raw / (sub_raw + cmp_raw + 1e-9)

        # PCS share (0..1). If no denominator, treat as zero (no special PCS protection).
        pcs_share = (pcs_mass / pcs_den) if pcs_den > 0 else 0.0
        pcs_share = float(max(0.0, min(1.0, pcs_share)))

        # Apply PCS penalty: more PCS => less AI risk
        job_risk = base * (1.0 - pcs_share)
        job_risk = float(max(0.0, min(1.0, job_risk)))

        rows.append({"job_id": job_id, "base": base, "pcs_share": pcs_share, "job_risk": job_risk})

    job_df = pd.DataFrame(rows)
    if job_df.empty:
        conn.execute("DELETE FROM job_profile")
        conn.execute("DELETE FROM job_risk")
        conn.commit()
        return

    # Global min–max normalization of job_risk (A-style, neutral)
    lo, hi = float(job_df["job_risk"].min()), float(job_df["job_risk"].max())
    if hi == lo:
        job_df["risk_norm"] = 0.5
    else:
        job_df["risk_norm"] = (job_df["job_risk"] - lo) / (hi - lo)

    # Write job_profile (pcs_share) and job_risk (normalized)
    with conn:
        conn.execute("DELETE FROM job_profile")
        conn.execute("DELETE FROM job_risk")
        job_df[["job_id", "pcs_share"]].to_sql("job_profile", conn, if_exists="append", index=False)
        job_df[["job_id", "risk_norm"]].rename(columns={"risk_norm": "risk"}).to_sql(
            "job_risk", conn, if_exists="append", index=False
        )
