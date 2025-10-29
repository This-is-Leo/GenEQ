"""
main.py (clean)

FastAPI app for PathBuilder AI risk scoring.

What this service provides:
- On startup: normalizes province/ethnicity raw exposures and computes job risks.
- /meta endpoints: lists of provinces, ethnicities, and jobs for the UI.
- /score endpoint: returns a combined risk score with weights that taper
  province + ethnicity toward zero for PCS-heavy jobs (physical/creative/social).

Design choices:
- Final score = w_p * province_risk + w_e * ethnicity_risk + w_j * job_risk
- Taper rule: as pcs_share -> 1, w_p -> 0 and w_e -> 0, all weight goes to w_j.
- No DB-stored weights; simple constants below.
"""

from __future__ import annotations

import os, json
import sqlite3
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from backend.compute import normalize_dimension, compute_job_risk
from backend.config import DB_PATH

# ------------------------------------------------------------
# Weight settings (base before taper)
# These are the defaults when pcs_share = 0 (no PCS emphasis)
# Sum should be 1.0
# ------------------------------------------------------------
BASE_W_PROVINCE = 0.10
BASE_W_ETHNICITY = 0.15
BASE_W_JOB = 0.75

# Sanity guard: ensure they sum to ~1.0
_total = BASE_W_PROVINCE + BASE_W_ETHNICITY + BASE_W_JOB
if abs(_total - 1.0) > 1e-6:
    # Simple normalization if someone changes the constants
    BASE_W_PROVINCE /= _total
    BASE_W_ETHNICITY /= _total
    BASE_W_JOB /= _total

app = FastAPI(title="PathBuilder AI Risk API", version="1.0.0")


# ------------------------------------------------------------
# Simple DB helpers
# ------------------------------------------------------------
def q1(sql: str, params=()):
    """Return first row as dict or None."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def qall(sql: str, params=()):
    """Return all rows as list[dict]."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def get_job_features(job_id: str) -> dict[str, float]:
    """
    Reads the features_json for job_id from job_features_raw and returns a {feature: value} dict.
    """
    row = q1("SELECT features_json FROM job_features_raw WHERE job_id=?", (job_id,))
    if not row or not row.get("features_json"):
        raise HTTPException(status_code=404, detail=f"No features found for job_id={job_id}")
    try:
        return json.loads(row["features_json"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Corrupt features_json for {job_id}: {e}")

def top_bottom_20(features: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """
    Mirrors your friend's logic: sort descending, take head(20) + tail(20).
    (Equivalent to taking top 20 largest and bottom 20 smallest.)
    """
    # Sort by value (desc)
    items = sorted(features.items(), key=lambda kv: kv[1], reverse=True)
    top20 = dict(items[:20])
    tail20 = dict(items[-20:])  # lowest 20
    return top20, tail20

# ------------- request/response models -------------
class AdviceRequest(BaseModel):
    job_id: str

class AdviceResponse(BaseModel):
    # The response is the JSON returned by the model; we keep it as an opaque dict
    result: dict[str, Any]

# ------------- OpenAI client -------------
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)

# ------------- system prompt (JSON only, mirrors your friend's file) -------------
SYSTEM_PROMPT = """
You are a professional career advisor specialized in AI impact on jobs.
Create a detailed JSON recommendation based on Canadian occupation classification and AI skill impact scores.
Maximize detail and reasoning. Ensure each pathway is AI-relevant.

IMPORTANT:
- Output ONLY valid JSON.
- Do NOT include text, titles, or explanations outside the JSON.

JSON format EXACTLY as follows:

{
  "Top_3_Pathways": {
    "Pathway_1": {"Tools_needed": "", "Relevance": ""},
    "Pathway_2": {"Tools_needed": "", "Relevance": ""},
    "Pathway_3": {"Tools_needed": "", "Relevance": ""}
  },
  "Recommended_Upskilling_Path": {
    "Step_1": {"Pathway": "", "Tools_needed": "", "Reasoning": ""},
    "Step_2": {"Pathway": "", "Tools_needed": "", "Reasoning": ""},
    "Your_Pick": ""
  }
}

Use top 2 pathways from the top 3 to suggest the personalized upskilling path.
"""


# ------------------------------------------------------------
# Weight tapering by PCS share
# As pcs_share -> 1, province/ethnicity -> 0, job -> 1
# ------------------------------------------------------------
def tapered_weights(pcs_share: float) -> Dict[str, float]:
    """
    Smoothly taper province/ethnicity weight by PCS share.
    pcs_share is in [0,1], computed in compute_job_risk() and stored in job_profile.
    """
    pcs = max(0.0, min(1.0, float(pcs_share)))
    w_p = BASE_W_PROVINCE * (1.0 - pcs)
    w_e = BASE_W_ETHNICITY * (1.0 - pcs)
    w_j = 1.0 - (w_p + w_e)  # give remainder to job
    # Final clamp in case of numerical fuzz
    s = w_p + w_e + w_j
    return {
        "province": w_p / s if s else 0.0,
        "ethnicity": w_e / s if s else 0.0,
        "job": w_j / s if s else 1.0,
    }


# ------------------------------------------------------------
# Band helper (simple, readable thresholds)
# ------------------------------------------------------------
def band(score: float) -> str:
    if score < 0.33:
        return "Low"
    if score < 0.66:
        return "Medium"
    return "High"


# ------------------------------------------------------------
# Startup: normalize province/ethnicity and compute job risks
# ------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    with sqlite3.connect(DB_PATH) as conn:
        # Normalize province exposure -> province_risk
        normalize_dimension(
            conn,
            table_raw="province_risk_raw",
            key_col="province_code",
            table_out="province_risk",
            out_key_col="province_code",
            out_val_col="risk",
        )

        # Normalize ethnicity exposure -> ethnicity_risk
        normalize_dimension(
            conn,
            table_raw="ethnicity_risk_raw",
            key_col="ethnicity_code",
            table_out="ethnicity_risk",
            out_key_col="ethnicity_code",
            out_val_col="risk",
        )

        # Compute job_risk and job_profile (pcs_share)
        compute_job_risk(conn)


# ------------------------------------------------------------
# Admin endpoint to recompute on demand
# ------------------------------------------------------------
@app.get("/admin/recompute")
def admin_recompute():
    with sqlite3.connect(DB_PATH) as conn:
        normalize_dimension(
            conn, "province_risk_raw", "province_code", "province_risk", "province_code", "risk"
        )
        normalize_dimension(
            conn, "ethnicity_risk_raw", "ethnicity_code", "ethnicity_risk", "ethnicity_code", "risk"
        )
        compute_job_risk(conn)
    return {"status": "ok", "message": "Recomputed normalized risks and job_risk."}


# ------------------------------------------------------------
# Meta endpoints for dropdowns
# ------------------------------------------------------------
@app.get("/meta/provinces")
def list_provinces():
    return qall("SELECT code, name FROM provinces ORDER BY name")


@app.get("/meta/ethnicities")
def list_ethnicities():
    return qall("SELECT code, name FROM ethnicities ORDER BY name")


@app.get("/meta/jobs")
def list_jobs():
    # Return ALL titles mapped to job_id for a great search experience
    return qall("SELECT job_id, title FROM job_titles ORDER BY title")

@app.post("/advice", response_model=AdviceResponse)
def advice(req: AdviceRequest):
    # 1) Get job display name (nice for the prompt)
    job_row = q1("SELECT title FROM jobs WHERE job_id=?", (req.job_id,))
    if not job_row:
        raise HTTPException(status_code=404, detail=f"Unknown job_id={req.job_id}")
    job_title = job_row["title"]

    # 2) Get features -> top/bottom 20 (same logic as friend's code)
    feats = get_job_features(req.job_id)
    top20, tail20 = top_bottom_20(feats)

    data_dict = {
        "NOC_or_Title": job_title,
        "Top_20_Skills": top20,
        "Tail_20_Skills": tail20
    }

    # 3) Call OpenAI chat completions (same model & settings your friend used)
    client = get_openai_client()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Occupation data:\n{json.dumps(data_dict)}"},
        ],
        max_tokens=2000,
        temperature=0,
        top_p=1,
    )

    raw = resp.choices[0].message.content.strip().strip("`").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # if model accidentally returns text around JSON, try to salvage
        begin = raw.find("{")
        end = raw.rfind("}")
        if begin != -1 and end != -1 and end > begin:
            payload = json.loads(raw[begin:end+1])
        else:
            raise HTTPException(status_code=500, detail=f"Failed to parse JSON from model: {raw[:300]}...")

    return AdviceResponse(result=payload)

# ------------------------------------------------------------
# /score API
# ------------------------------------------------------------
class ScoreRequest(BaseModel):
    province_code: str
    ethnicity_code: str
    job_id: str


class ScoreResponse(BaseModel):
    inputs: Dict[str, str]
    components: Dict[str, float]
    weights: Dict[str, float]
    score: float
    band: str


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest):
    # Components: fetch from normalized tables
    pr = q1("SELECT risk FROM province_risk WHERE province_code=?", (req.province_code,))
    er = q1("SELECT risk FROM ethnicity_risk WHERE ethnicity_code=?", (req.ethnicity_code,))
    jr = q1("SELECT risk FROM job_risk WHERE job_id=?", (req.job_id,))
    jp = q1("SELECT pcs_share FROM job_profile WHERE job_id=?", (req.job_id,))

    missing = []
    if not pr:
        missing.append("province_risk (normalized)")
    if not er:
        missing.append("ethnicity_risk (normalized)")
    if not jr:
        missing.append("job_risk (computed)")
    if not jp:
        missing.append("job_profile (pcs_share)")
    if missing:
        raise HTTPException(status_code=422, detail={"error": "Missing components", "missing": missing})

    components = {
        "province": float(pr["risk"]),
        "ethnicity": float(er["risk"]),
        "job": float(jr["risk"]),
    }

    pcs_share = float(jp["pcs_share"])
    weights = tapered_weights(pcs_share)

    # Simple weighted sum (clear + explainable)
    score_val = (
        components["province"] * weights["province"]
        + components["ethnicity"] * weights["ethnicity"]
        + components["job"] * weights["job"]
    )
    score_val = max(0.0, min(1.0, float(score_val)))

    # Pretty input names for UI
    in_prov = q1("SELECT name FROM provinces WHERE code=?", (req.province_code,)) or {
        "name": req.province_code
    }
    in_eth = q1("SELECT name FROM ethnicities WHERE code=?", (req.ethnicity_code,)) or {
        "name": req.ethnicity_code
    }
    in_job = q1("SELECT title FROM jobs WHERE job_id=?", (req.job_id,)) or {"title": req.job_id}

    # Round components and weights for display
    components_rounded = {k: round(v, 2) for k, v in components.items()}
    weights_rounded    = {k: round(v, 2) for k, v in weights.items()}

    return ScoreResponse(
        inputs={"province": in_prov["name"], "ethnicity": in_eth["name"], "job": in_job["title"]},
        components=components_rounded,
        weights=weights_rounded,
        score=round(score_val, 2),
        band=band(score_val)
    )
