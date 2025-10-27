# frontend/app.py  — Streamlit-only, no HTTP calls
import sqlite3
import streamlit as st
from typing import Dict

import sys, os
# add project root (folder that contains 'backend' and 'frontend') to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.config import DB_PATH, W_PROVINCE, W_ETHNICITY, W_JOB
from backend.compute import normalize_dimension, compute_job_risk

st.set_page_config(page_title="PathBuilder AI — Risk Check (MVP)", layout="centered")

# ---------- DB helpers ----------
def get_conn():
    # Streamlit runs in a single process; keep connection short-lived
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def q1(conn, sql, params=()):
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None

def qall(conn, sql, params=()):
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]

def ensure_ready():
    """If normalized tables or job_risk are empty, recompute quickly."""
    with get_conn() as conn:
        # province/ethnicity normalization present?
        p_cnt = q1(conn, "SELECT COUNT(*) AS c FROM province_risk")["c"] if q1(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name='province_risk'") else 0
        e_cnt = q1(conn, "SELECT COUNT(*) AS c FROM ethnicity_risk")["c"] if q1(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name='ethnicity_risk'") else 0
        j_cnt = q1(conn, "SELECT COUNT(*) AS c FROM job_risk")["c"] if q1(conn, "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name='job_risk'") else 0

        if p_cnt == 0:
            normalize_dimension(conn, "province_risk_raw", "province_code", "province_risk", "province_code", "risk")
        if e_cnt == 0:
            normalize_dimension(conn, "ethnicity_risk_raw", "ethnicity_code", "ethnicity_risk", "ethnicity_code", "risk")
        if j_cnt == 0:
            compute_job_risk(conn)

@st.cache_data(ttl=300)
def load_options():
    ensure_ready()
    with get_conn() as conn:
        provinces   = qall(conn, "SELECT code, name FROM provinces ORDER BY name")
        ethnicities = qall(conn, "SELECT code, name FROM ethnicities ORDER BY name")
        jobs        = qall(conn, "SELECT job_id, title FROM job_titles ORDER BY title")
    return provinces, ethnicities, jobs

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
    w_p = W_PROVINCE * (1.0 - pcs)
    w_e = W_ETHNICITY * (1.0 - pcs)
    w_j = 1.0 - (w_p + w_e)  # remainder goes to job
    s = w_p + w_e + w_j
    return {
        "province": w_p / s if s else 0.0,
        "ethnicity": w_e / s if s else 0.0,
        "job": w_j / s if s else 1.0,
    }

def band(score: float) -> str:
    if score < 0.33:
        return "Low"
    if score < 0.66:
        return "Medium"
    return "High"


def compute_score_local(province_code: str, ethnicity_code: str, job_id: str):
    ensure_ready()
    with get_conn() as conn:
        pr = q1(conn, "SELECT risk FROM province_risk WHERE province_code=?", (province_code,))
        er = q1(conn, "SELECT risk FROM ethnicity_risk WHERE ethnicity_code=?", (ethnicity_code,))
        jr = q1(conn, "SELECT risk FROM job_risk WHERE job_id=?", (job_id,))

        if not (pr and er and jr):
            missing = []
            if not pr: missing.append("province_risk")
            if not er: missing.append("ethnicity_risk")
            if not jr: missing.append("job_risk")
            raise RuntimeError(f"Missing components: {', '.join(missing)}")

        components = {
            "province": float(pr["risk"]),
            "ethnicity": float(er["risk"]),
            "job": float(jr["risk"]),
        }

        # fetch pcs_share and taper weights
        jp = q1(conn, "SELECT pcs_share FROM job_profile WHERE job_id=?", (job_id,))
        if not jp:
            raise RuntimeError("Missing component: job_profile (pcs_share)")
        pcs_share = float(jp["pcs_share"])
        weights = tapered_weights(pcs_share)

        score_val = sum(components[k] * weights[k] for k in components)
        score_val = max(0.0, min(1.0, score_val))

        # Pretty rounding for display
        return {
            "inputs": {
                "province": q1(conn, "SELECT name FROM provinces WHERE code=?", (province_code,))["name"],
                "ethnicity": q1(conn, "SELECT name FROM ethnicities WHERE code=?", (ethnicity_code,))["name"],
                "job": q1(conn, "SELECT title FROM job_titles WHERE job_id=? ORDER BY title LIMIT 1", (job_id,))["title"],
            },
            "components": {k: round(v, 2) for k, v in components.items()},
            "weights": {k: round(v, 2) for k, v in weights.items()},
            "score": round(score_val, 2),
            "band": band(score_val),
        }

# ---------- UI ----------
st.title("PathBuilder AI")
st.caption("Select your details to compute an AI disruption risk score.")

provinces, ethnicities, jobs = load_options()

# Nice display labels for dropdowns
prov_disp = [f"{p['name']}" for p in provinces]
eth_disp  = [f"{e['name']}" for e in ethnicities]
job_disp  = [j["title"] for j in jobs]

col1, col2 = st.columns(2)
with col1:
    p_idx = st.selectbox("Province/Territory", prov_disp, index=0)
with col2:
    e_idx = st.selectbox("Ethnicity (Statistics Canada categories)", eth_disp, index=0)

j_idx = st.selectbox("Job Title", job_disp, index=0)

if st.button("Calculate Risk"):
    sel_prov = provinces[prov_disp.index(p_idx)]["code"]
    sel_eth  = ethnicities[eth_disp.index(e_idx)]["code"]
    sel_job  = jobs[job_disp.index(j_idx)]["job_id"]

    try:
        result = compute_score_local(sel_prov, sel_eth, sel_job)
        st.subheader(f"AI Risk Score: {result['score']}")
        st.caption(f"Band: **{result['band']}**")
        st.json(result)
    except Exception as ex:
        st.error(str(ex))
