# 🗺️ PathBuilder AI: Equitable Workforce Transition Tool

PathBuilder AI is a workforce navigation prototype that helps users assess their AI job disruption risk, discover personalized upskilling pathways, and connect with volunteer mentors in their field. Built with an equity-first design, it supports workers who face structural barriers in the AI economy.

### 🔗 Live Demo
https://gen-eq-pathbuilder.streamlit.app/

## 🚧 Problem Statement

Artificial Intelligence is rapidly transforming the labour market but not everyone is impacted equally:
- Routine and low-wage jobs face high automation risk
- These jobs are disproportionately held by women, newcomers, racialized groups, and non-degree workers
- Traditional career guidance assumes equal access to time, money, and training
- Without intervention, AI will widen income inequality and workforce exclusion

Goal: Build a scalable, ethical, and practical transition tool that empowers workers, especially those in vulnerable jobs to prepare for the AI economy.

## ⚙️ Current Prototype Features

PathBuilder AI empowers workers with personalized and accessible career transitions:

Feature | Description 
| --- | --- |
AI Risk Score | Calculates personalized AI risk based on job title + province + ethnicity using labour exposure data sourced from Statistics Canada and a skill vulnerability model
AI Upskilling Advisor (LLM-powered) | Suggests 3 personalized career pathways + skill/tool suggestions + a recommended upskilling plan using AI
Mentor Connect (Community Support Layer) | Users can book a 1:1 session with volunteer mentors based on industry, expertise, and availability

## 🏛️ Architecture Overview

### How Risk Score Works

Risk is calculated using 3 components:

Component |	Purpose
|---|---|
Province Risk |	AI exposure by geography (StatsCan labour trends)
Ethnicity Risk | Exposure risk by visible minority group (equity lens)
Job Risk | Based on skill vulnerability to AI substitution

- Each job is scored using 82 skills and abilities
- Routine skills increase risk
- Physical, social, and creative abilities protect against AI risk
- All scores normalized 0–1 scale

### Data Behind AI Risk Model
Dataset | Purpose
|---|---|
SkillsAbilitiesMerged.csv | 900+ occupations × 82 skills
AbilitySkillRubric.csv | AI Substitution & Complementarity Index
Custom Category Map | Clusters skills into Routine/Physical/Creative/Social


## 🎯 Next Steps

- Build volunteer signup portal (currently mentors are seed data)
- Add Admin Dashboard for:
    - Approving mentors
    - Managing bookings and spam prevention
- Add database management and security features to protect user data
- Build local LLM to avoid vendor lock-in
- Employer partnership integration
