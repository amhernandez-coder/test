# Stonebridge Scheduler – Streamlit (Minimal)

**Important:** The file must be named exactly `app.py` (not `app.apy`).

## Quick Deploy (Streamlit Community Cloud)
1. Create a new repo on GitHub and upload **two files** at the repo root:  
   - `app.py` (this file)  
   - `requirements.txt` (contents below)
2. On Streamlit Cloud: **New app** → select your repo → **Main file path** = `app.py` → Deploy.

### requirements.txt
```
streamlit>=1.35.0
pandas>=2.2.0
openpyxl>=3.1.0
```

## How to Use
- Upload your **roster** export (CSV or XLSX). Required columns (case-insensitive):  
  `site, date (YYYY-MM-DD), modality, role (interviewer|tester|solo), provider`  
- Optionally upload a **Provider Master** (CSV/XLSX) with columns:  
  `provider, language (English/Spanish), is_spanish (true/false), preferred_tester`  
- Click **Run pairings** and then **Download Google Calendar CSV** (all-day events).  
- Titles abbreviate **San Antonio → SA** to save space and include Pairing/GAP/SOLO cues.
