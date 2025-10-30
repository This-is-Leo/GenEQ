# frontend/app.py  — Streamlit-only, no HTTP calls
import sqlite3
import streamlit as st
from typing import Dict
from openai import OpenAI
import json
import sys, os
import datetime as dt
from contextlib import closing


# add project root (folder that contains 'backend' and 'frontend') to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.config import DB_PATH, W_PROVINCE, W_ETHNICITY, W_JOB
from backend.compute import normalize_dimension, compute_job_risk

st.set_page_config(page_title="PathBuilder AI", layout="centered")

# ---------- DB helpers ----------
def db():
    # same DB the rest of the app uses
    return sqlite3.connect("db/risk.db", check_same_thread=False)

def list_volunteers(field_filter=None, q=None):
    with closing(db()) as conn, closing(conn.cursor()) as cur:
        sql = "SELECT volunteer_id, name, school, field, email, bio, skills FROM volunteers"
        params = []
        clauses = []
        if field_filter and field_filter != "All":
            clauses.append("field = ?")
            params.append(field_filter)
        if q:
            clauses.append("(name LIKE ? OR skills LIKE ? OR bio LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY name"
        cur.execute(sql, params)
        return cur.fetchall()

def list_open_slots(volunteer_id):
    with closing(db()) as conn, closing(conn.cursor()) as cur:
        cur.execute("""SELECT slot_id, start_utc, end_utc
                       FROM volunteer_slots
                       WHERE volunteer_id=? AND is_booked=0
                       ORDER BY start_utc""", (volunteer_id,))
        return cur.fetchall()

def create_booking(volunteer_id, slot_id, user_name, user_email, topic):
    with closing(db()) as conn, closing(conn.cursor()) as cur:
        # Reserve the slot in a tiny transaction
        cur.execute("SELECT is_booked FROM volunteer_slots WHERE slot_id=? AND volunteer_id=?",
                    (slot_id, volunteer_id))
        row = cur.fetchone()
        if not row:
            return False, "Slot not found."
        if row[0] == 1:
            return False, "Sorry, that slot was just booked."

        cur.execute("""INSERT INTO bookings(volunteer_id, slot_id, user_name, user_email, topic)
                       VALUES (?,?,?,?,?)""", (volunteer_id, slot_id, user_name, user_email, topic))
        cur.execute("UPDATE volunteer_slots SET is_booked=1 WHERE slot_id=?", (slot_id,))
        conn.commit()
        return True, "Session booked! You’ll receive a confirmation in-app."

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

@st.cache_data(ttl=300)
def fetch_teer_weight(job_id: str) -> float:
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT COALESCE(teer_weight, 0) FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return float(row[0]) if row else 0.0
    finally:
        conn.close()

def get_openai_client() -> OpenAI:
    # Read from Streamlit Secrets in the cloud
    OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY is missing. Add it in Settings → Secrets.")
        st.stop()
    return OpenAI(api_key=OPENAI_API_KEY)

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
    if score < 0.35:
        return "Low"
    if score < 0.65:
        return "Medium"
    return "High"

# Utility: clamp a number to a range [low, high]
def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Restrict a numeric value to stay within [low, high]."""
    return max(low, min(high, float(value)))

# Map UI string to multiplier (keep your current labels)
EXP_MULT = {"Entry (0-2 years)": 1.00, "Mid (3-7 years)": 0.80, "Senior (8+ years)": 0.60}

def compute_score_local(province_code: str, ethnicity_code: str, job_id: str, experience_label: str):
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

        # Base components (0..1)
        province_risk = float(pr["risk"])
        ethnicity_risk = float(er["risk"])
        job_risk = float(jr["risk"])

        # === EXPERIENCE COMPONENT (0..1; HIGHER = MORE RISK) ===
        # Pull the CSV-provided replaceability weight stored in `jobs.teer_weight`
        row = q1(conn, "SELECT teer_weight FROM jobs WHERE job_id=?", (job_id,))
        teer_weight = float(row["teer_weight"]) if row and row["teer_weight"] is not None else 0.0
        teer_weight = clamp(teer_weight, 0.0, 1.0)

        # Support both hyphen and en-dash labels from the UI
        label_norm = experience_label.replace("–", "-")
        exp_mult_map = {
            "Entry (0-2 years)": 1.00,
            "Mid (3-7 years)":   0.80,
            "Senior (8+ years)": 0.60
        }
        exp_mult = exp_mult_map.get(label_norm, 1.00)

        # Risk rises with TEER replaceability and falls with experience seniority
        experience_component = clamp(teer_weight * exp_mult, 0.0, 1.0)

        # === WEIGHTS (sum = 1.0) ===
        WEIGHTS = {
            "job":        0.60,
            "province":   0.15,
            "ethnicity":  0.10,
            "experience": 0.15,
        }

        # Composite: ADD all components; each is already a 0..1 "more = higher risk"
        composite = (
            WEIGHTS["job"]        * job_risk +
            WEIGHTS["province"]   * province_risk +
            WEIGHTS["ethnicity"]  * ethnicity_risk +
            WEIGHTS["experience"] * experience_component
        )
        final_score = clamp(composite, 0.0, 1.0)

        return {
            "inputs": {
                "province":   q1(conn, "SELECT name FROM provinces WHERE code=?", (province_code,))["name"],
                "ethnicity":  q1(conn, "SELECT name FROM ethnicities WHERE code=?", (ethnicity_code,))["name"],
                "job":        q1(conn, "SELECT title FROM job_titles WHERE job_id=? ORDER BY title LIMIT 1", (job_id,))["title"],
                "experience": experience_label,
            },
            "components": {
                "job":        round(job_risk, 2),
                "province":   round(province_risk, 2),
                "ethnicity":  round(ethnicity_risk, 2),
                "experience": round(experience_component, 2),
            },
            "weights": WEIGHTS,
            "score": round(final_score, 2),
            "band": band(final_score),
        }

    
def get_job_features_local(job_id: str) -> dict[str, float]:
    with get_conn() as conn:
        row = q1(conn, "SELECT features_json FROM job_features_raw WHERE job_id=?", (job_id,))
        if not row or not row.get("features_json"):
            raise RuntimeError(f"No features found for job_id={job_id}")
        return json.loads(row["features_json"])

def top_bottom_20_local(features: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    items = sorted(features.items(), key=lambda kv: kv[1], reverse=True)
    top20 = dict(items[:20])
    tail20 = dict(items[-20:])
    return top20, tail20

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

# ---------- UI helpers ----------
def render_risk_result(result: dict):
    # Header metric + progress bar
    st.subheader("AI Risk Score")
    colA, colB = st.columns([1, 3])
    with colA:
        st.metric(label="Overall Score (0-1)", value=f"{result['score']:.2f}")
        st.caption(f"Band: **{result['band']}**")
    with colB:
        st.progress(min(max(result["score"], 0.0), 1.0))

    # Components and Weights, side by side
    st.markdown("#### Breakdown")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Components (normalized 0-1)**")
        for k, v in result["components"].items():
            st.write(f"- **{k.title()}**: `{v:.2f}`")
    with c2:
        st.markdown("**Weights (sum = 1.0)**")
        for k, v in result["weights"].items():
            st.write(f"- **{k.title()}**: `{v:.2f}`")

    # Inputs in an expander to avoid clutter
    with st.expander("Details • Inputs used"):
        st.write(
            f"- **Province/Territory**: {result['inputs']['province']}\n"
            f"- **Ethnicity**: {result['inputs']['ethnicity']}\n"
            f"- **Job Title**: {result['inputs']['job']}\n"
            f"- **Experience**: {result['inputs'].get('experience', '-')}"
        )


def render_pathways(payload: dict):
    # Top 3 pathways as simple cards
    st.subheader("Top Career Pathways")
    top = payload.get("Top_3_Pathways", {})
    for label in ["Pathway_1", "Pathway_2", "Pathway_3"]:
        p = top.get(label, {})
        with st.container(border=True):
            st.markdown(f"**{label.replace('_', ' ')}**")
            st.write(f"**Tools needed:** {p.get('Tools_needed', '—')}")
            st.caption(p.get("Relevance", ""))

    # Recommended upskilling path as a numbered plan
    st.subheader("Recommended Upskilling Path")
    rec = payload.get("Recommended_Upskilling_Path", {})
    for step in ["Step_1", "Step_2"]:
        s = rec.get(step, {})
        with st.container(border=True):
            st.markdown(f"**{step.replace('_', ' ')}: {s.get('Pathway', '—')}**")
            st.write(f"**Tools needed:** {s.get('Tools_needed', '—')}")
            st.caption(s.get("Reasoning", ""))

    your_pick = rec.get("Your_Pick")
    if your_pick:
        st.info(f"**Your Pick:** {your_pick}")


# ---------- UI ----------
st.title("PathBuilder AI")
st.caption("Select your details to compute an AI disruption risk score.")

provinces, ethnicities, jobs = load_options()

# Nice display labels for dropdowns
prov_disp = [f"{p['name']}" for p in provinces]
eth_disp  = [f"{e['name']}" for e in ethnicities]
job_disp  = [j["title"] for j in jobs]
exp_disp = ["Entry (0-2 years)", "Mid (3-7 years)", "Senior (8+ years)"]

col1, col2 = st.columns(2)
with col1:
    p_idx = st.selectbox("Province/Territory", prov_disp, index=0)
with col2:
    e_idx = st.selectbox("Ethnicity (Statistics Canada categories)", eth_disp, index=0)

j_idx = st.selectbox("Job Title", job_disp, index=0)
exp_idx  = st.selectbox("Experience level", exp_disp, index=0)

tab1, tab2, tab3 = st.tabs(["Risk Score", "Career Pathways (AI Advisor)", "Mentor Connect"])

with tab1:
    if st.button("Calculate Risk"):
        sel_prov = provinces[prov_disp.index(p_idx)]["code"]
        sel_eth  = ethnicities[eth_disp.index(e_idx)]["code"]
        sel_job  = jobs[job_disp.index(j_idx)]["job_id"]
        sel_exp  = exp_idx  

        try:
            result = compute_score_local(sel_prov, sel_eth, sel_job, sel_exp)
            render_risk_result(result)
        except Exception as ex:
            st.error(str(ex))


with tab2:
    st.write("Get tailored career pathways and upskilling steps based on your occupation’s skill profile.")
    if st.button("Generate Career Pathways"):
        sel_job  = jobs[job_disp.index(j_idx)]["job_id"]
        job_name = q1(get_conn(), "SELECT title FROM jobs WHERE job_id=?", (sel_job,))["title"]

        try:
            feats = get_job_features_local(sel_job)
            top20, tail20 = top_bottom_20_local(feats)

            data_dict = {
                "NOC_or_Title": job_name,
                "Top_20_Skills": top20,
                "Tail_20_Skills": tail20
            }

            client = get_openai_client()
            with st.spinner("Generating career pathways..."):
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
                begin = raw.find("{"); end = raw.rfind("}")
                if begin != -1 and end != -1 and end > begin:
                    payload = json.loads(raw[begin:end+1])
                else:
                    st.error("Failed to parse JSON from model.")
                    st.code(raw)
                    st.stop()

            st.subheader("AI Career Recommendation")
            render_pathways(payload)


        except Exception as ex:
            st.error(str(ex))


with tab3:
    st.subheader("Find a student mentor and book a virtual session")

    # Filters
    colA, colB = st.columns([1, 1])
    with colA:
        field = st.selectbox("Area of study", ["All", "Data Analytics", "Software Engineering", "Marketing", "Finance"])
    with colB:
        q = st.text_input("Search (name/skills)")

    rows = list_volunteers(field_filter=field, q=q)
    if not rows:
        st.info("No volunteers match your filters yet.")
    else:
        for v_id, name, school, vfield, email, bio, skills in rows:
            with st.expander(f"{name} — {vfield} ({school})"):
                st.write(bio or "—")
                if skills:
                    st.caption(f"**Skills:** {skills}")

                open_slots = list_open_slots(v_id)
                if not open_slots:
                    st.warning("No open slots at the moment.")
                    continue

                # slot picker
                slot_labels = [f"{dt.datetime.fromisoformat(s).strftime('%b %d, %H:%M')} UTC"
                               for _, s, _ in open_slots]
                slot_map = {lbl: sid for (sid, s, _), lbl in zip(open_slots, slot_labels)}
                choose = st.selectbox("Pick a time:", slot_labels, key=f"slot_{v_id}")

                # booking form
                with st.form(f"book_{v_id}"):
                    u_name  = st.text_input("Your name")
                    u_email = st.text_input("Your email")
                    topic   = st.text_area("What do you want help with? (optional)")
                    submit  = st.form_submit_button("Book this session")
                    if submit:
                        if not u_name or not u_email:
                            st.error("Name and email are required.")
                        else:
                            ok, msg = create_booking(v_id, slot_map[choose], u_name, u_email, topic)
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)


