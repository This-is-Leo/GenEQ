# PathBuilder AI – Equitable Workforce Transition Tool

PathBuilder AI is a prototype decision-support tool that helps workers assess their risk of AI-driven job disruption and discover equitable upskilling pathways. It is designed with an equity-first lens to ensure vulnerable workers are not left behind in the AI economy.

## 🚧 Problem Statement

Artificial Intelligence is transforming the labour market faster than workers and institutions can keep up. The risks are not equally distributed:
- Routine and low-wage jobs face high automation risk
- These jobs are disproportionately held by women, newcomers, racialized groups, and non-degree workers
- Current upskilling systems assume equal access to time, cost, and training, which is not realistic
- Without intervention, AI will widen inequality and restrict economic mobility

Goal: Build a scalable, ethical solution that supports equitable career transitions, wage resilience, and inclusive participation in the AI economy.

## ⚙️ Solution Prototype

PathBuilder AI empowers workers with personalized and accessible career transitions:

Feature	Description
- AI Risk Assessment: Measures automation risk based on occupational skills & abilities
- Transferable Pathways: Suggests safer, future-proof career options
- Upskilling Recommendations: Provides routes using free/low-cost programs & micro-credentials
- Equity Lens: Designed intentionally for accessibility and inclusion
- Transparent Design: Explainable logic using open data + fair scoring

## 🏛️ Architecture Overview
User Input -> Risk Scoring Model (Skills + AI Substitution Index) -> Transferable Skills Engine -> Pathway Output (LLM – Fine-tuned)

### 1. Risk Scoring Model

Risk is computed using three weighted factors:
Component     |       Source Data                                         |   Purpose
Province Risk | AI exposure levels by Canadian province                   |	Geographic vulnerability
Ethnicity Risk| Exposure risk by visible minority groups                  |	Equity context
Job Risk	  | Based on skills & abilities mapped to AI substitution risk|	Automation risk from skills

We use:
- SkillsAbilitiesMerged.csv (900 occupations × 82 skill dimensions)
- AbilitySkillRubric.csv (AI substitution vs complementarity index)
- Custom Category Mapping
    - Routine → high AI risk
    - Physical / Creative / Social → reduced AI risk
- Weighted formula reduces bias by factoring human-centric abilities.

## Tech Stack
Language: Python 3.10+
Frontend: Streamlit
Database: SQLite

## Run Locally
1. Clone and Install
```
git clone https://github.com/yourusername/geneq.git
cd geneq
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Initialize the Database
```
python init_db.py
```

3. Run the App
```
streamlit run frontend/app.py
```

## Next Steps
1. Transferable skills engine	
2. Personalized learning pathways	
3. AI assist via local LLM or GPT API	
