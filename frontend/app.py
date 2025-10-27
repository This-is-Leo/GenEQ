import streamlit as st, requests

st.set_page_config(page_title="PathBuilder AI", page_icon="🧭")
API_BASE = st.secrets.get("API_BASE", "http://localhost:8000")

@st.cache_data(ttl=300)
def fetch_options(endpoint):
    r = requests.get(f"{API_BASE}/meta/{endpoint}", timeout=10)
    r.raise_for_status()
    return r.json()

st.title("PathBuilder AI")
st.caption("Select your details to compute an AI disruption risk score.")

provinces   = fetch_options("provinces")
ethnicities = fetch_options("ethnicities")
jobs        = fetch_options("jobs")

prov_map = {p["name"]: p["code"] for p in provinces}
eth_map  = {e["name"]: e["code"] for e in ethnicities}
job_map  = {j["title"]: j["job_id"] for j in jobs}

col1, col2 = st.columns(2)
with col1:
    sel_prov = st.selectbox("Province/Territory", list(prov_map.keys()))
with col2:
    sel_eth  = st.selectbox("Ethnicity (Statistics Canada categories)", list(eth_map.keys()))
sel_job = st.selectbox("Job Title", list(job_map.keys()))

if st.button("Calculate Risk", type="primary"):
    payload = {"province_code": prov_map[sel_prov], "ethnicity_code": eth_map[sel_eth], "job_id": job_map[sel_job]}
    try:
        r = requests.post(f"{API_BASE}/score", json=payload, timeout=20)
        if r.status_code == 422:
            st.error(r.json())
        else:
            r.raise_for_status()
            data = r.json()
            st.metric("AI Risk Score", f"{data['score']:.2f}", help=f"Band: {data['band']}")
            st.progress(min(1.0, data["score"]))
            st.write({"Inputs": data["inputs"], "Components (0–1)": data["components"], "Weights": data["weights"], "Band": data["band"]})
    except Exception as e:
        st.error(str(e))
