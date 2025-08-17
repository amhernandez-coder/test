
import io
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stonebridge Scheduler – Streamlit (Deputy Auto‑Mapper)", layout="wide")

# -------------------- Helpers --------------------
def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def title_abbrev(site: str) -> str:
    if not site:
        return site
    s = site.lower()
    if "san antonio" in s or "san antonio behavioral" in s or s == "sa":
        return "SA"
    return site

def to_google_csv(rows):
    # Google Calendar all-day format
    cols = ["Subject","Start Date","Start Time","End Date","End Time","All Day Event","Description","Location"]
    df = pd.DataFrame(rows, columns=cols)
    df["All Day Event"] = "True"
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()

def load_tabular(uploaded_file) -> pd.DataFrame:
    # Accept CSV or XLSX
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)

def norm_col(df: pd.DataFrame):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

# ---------- Deputy Auto‑Mapper ----------
# Maps varied Deputy headers to our expected schema
ROSTER_ALIASES = {
    "site": ["site","location","work location","venue","clinic","office"],
    "date": ["date","shift date","start date","start","day","timesheet date"],
    "modality": ["modality","type","category","mode"],
    "role": ["role","area","position","duty","job","title"],
    "provider": ["provider","employee","employee name","name","staff"],
    "language": ["language","lang"],
}

def _pick(low: dict, aliases: list) -> str:
    for a in aliases:
        v = low.get(a)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""

def _to_iso_date(val: str) -> str:
    s = (val or "").strip()
    # Already ISO (YYYY-MM-DD)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # Try MM/DD/YYYY (optionally with time)
    if "/" in s:
        parts = s.split()[0].split("/")
        if len(parts) >= 3:
            mm = parts[0].zfill(2)
            dd = parts[1].zfill(2)
            yyyy = parts[2]
            if len(yyyy) == 2:
                yyyy = "20" + yyyy
            return f"{yyyy}-{mm}-{dd}"
    # Fallback: return as-is
    return s[:10]

def normalize_row_strict(row: pd.Series) -> dict:
    # expects exact headers
    get = lambda k: str(row.get(k,"")).strip()
    site = get("site")
    date = get("date")
    modality = get("modality")
    role = get("role").lower()
    provider = get("provider")
    language = get("language").lower() if get("language") else "english"
    return {"site": site, "date": date, "modality": modality, "role": role, "provider": provider, "language": language}

def normalize_row_deputy(row: pd.Series) -> dict:
    low = {str(k).strip().lower(): row[k] for k in row.index}
    site = _pick(low, ROSTER_ALIASES["site"])
    date_raw = _pick(low, ROSTER_ALIASES["date"])
    date = _to_iso_date(date_raw)
    modality = _pick(low, ROSTER_ALIASES["modality"])
    role_guess = _pick(low, ROSTER_ALIASES["role"]).lower()
    provider = _pick(low, ROSTER_ALIASES["provider"])
    language = (_pick(low, ROSTER_ALIASES["language"]) or "English").lower()

    # Infer modality if missing
    if not modality:
        modality = "Telehealth" if "tele" in (site or "").lower() else "Live"

    # Normalize role into interviewer|tester|solo
    role = role_guess
    if role not in {"interviewer","tester","solo"}:
        if any(k in role_guess for k in ["tester","lpa","psychometric"]):
            role = "tester"
        elif any(k in role_guess for k in ["solo","independent"]):
            role = "solo"
        else:
            role = "interviewer"

    return {"site": site, "date": date, "modality": modality, "role": role, "provider": provider, "language": language}

def normalize_roster(df: pd.DataFrame) -> pd.DataFrame:
    strict = df.apply(normalize_row_strict, axis=1, result_type="expand")
    # If strict seems invalid (missing key cols or many empties), fall back to Deputy mapping
    required = ["site","date","modality","role","provider"]
    if strict[required].replace("", pd.NA).isna().any().any():
        mapped = df.apply(normalize_row_deputy, axis=1, result_type="expand")
        return mapped
    return strict

# ---------- Language & preferences ----------
SPANISH_SET = {
    "cintia martinez","liliana pizana","emma thomae","ben aguilar","cesar villarreal",
    "teresa castano","dr. alvarez-sanders","alvarez-sanders","belinda castillo","noemi martinez"
}

def build_master_maps(master_df: pd.DataFrame):
    # Optional Provider Master columns:
    # provider, language (English/Spanish), is_spanish (true/false), preferred_tester
    lang_map = {}
    pref_map = {}
    if master_df is None or master_df.empty:
        return lang_map, pref_map

    m = norm_col(master_df)
    for _, r in m.iterrows():
        prov = str(r.get("provider","")).strip()
        if not prov:
            continue
        lang_raw = str(r.get("language","")).strip().lower()
        is_spanish = str(r.get("is_spanish","")).strip().lower()
        lang = "spanish" if (is_spanish == "true" or lang_raw == "spanish") else ("english" if lang_raw=="english" else "")
        if lang:
            lang_map[prov.lower()] = lang
        pref = str(r.get("preferred_tester","")).strip()
        if pref:
            pref_map[prov.lower()] = pref
    return lang_map, pref_map

def get_lang(name: str, lang_map: dict):
    if not name:
        return "english"
    n = name.lower()
    if n in lang_map:
        return lang_map[n]
    return "spanish" if any(tok in n for tok in SPANISH_SET) else "english"

def preferred_score(interviewer: str, tester: str, lang_map: dict, pref_map: dict) -> int:
    i = (interviewer or "").lower()
    t = (tester or "").lower()
    # Hard-coded clinic prefs
    if "lakaii jones" in i and "virginia parker" in t: return 5
    if "lyn mcdonald" in i and "ed howarth" in t: return 5
    if "liliana pizana" in i and "emma thomae" in t: return 4
    # Master-file preference
    pref = pref_map.get(i)
    if pref and pref.lower() in t:
        return 4
    # Language match
    lang_i = get_lang(i, lang_map)
    lang_t = get_lang(t, lang_map)
    if lang_i == lang_t:
        return 2
    return 0

def generate_pairings(roster_df: pd.DataFrame, lang_map: dict, pref_map: dict):
    df = norm_col(roster_df)
    need_cols = {"site","date","modality","role","provider"}
    missing = need_cols - set(df.columns)
    if missing:
        raise ValueError(f"Roster missing required columns: {', '.join(sorted(missing))}")
    df = normalize_roster(df)

    # validate again after normalization
    missing_any = df[["site","date","modality","role","provider"]].replace("", pd.NA).isna().any().any()
    if missing_any:
        raise ValueError("Deputy file could not be normalized. Check headers like Location/Employee/Start Date, or share the first 5 header names.")

    grouped = df.groupby(["site","date","modality"], dropna=False)

    events = []
    violations = []
    gaps = []

    site_shift_counts = df.groupby("site")["provider"].count()
    provider_shift_counts = df.groupby("provider")["site"].count()

    for (site, date, modality), grp in grouped:
        interviewers = [r["provider"] for _, r in grp[grp["role"]=="interviewer"].iterrows()]
        testers = [r["provider"] for _, r in grp[grp["role"]=="tester"].iterrows()]
        solos = [r["provider"] for _, r in grp[grp["role"]=="solo"].iterrows()]

        available_testers = set(testers)

        for i_name in interviewers:
            best_t = None
            best_score = -1
            for t_name in list(available_testers):
                score = preferred_score(i_name, t_name, lang_map, pref_map)
                if score > best_score:
                    best_score = score
                    best_t = t_name
            if best_t:
                available_testers.remove(best_t)
                subject = f"{title_abbrev(site)} | Pairing: {i_name} + {best_t}"
                desc = f"Dyad pairing for {date} {modality}."
                if best_score >= 4: desc += " Preference satisfied."
                elif best_score == 2: desc += " Language-matched."
                events.append({
                    "Subject": subject, "Start Date": date, "Start Time": "", "End Date": date, "End Time": "",
                    "All Day Event": "True", "Description": desc, "Location": site
                })
                if best_score < 4 and ("lakaii jones" in i_name.lower() or "lyn mcdonald" in i_name.lower() or get_lang(i_name, lang_map) == "spanish"):
                    violations.append({"site": site, "date": date, "modality": modality, "type": "Preference Not Met", "interviewer": i_name, "tester": best_t})
            else:
                subject = f"{title_abbrev(site)} | GAP: {i_name} (no tester)"
                events.append({
                    "Subject": subject, "Start Date": date, "Start Time": "", "End Date": date, "End Time": "",
                    "All Day Event": "True", "Description": f"Unpaired interviewer. Needs tester for {modality}.", "Location": site
                })
                gaps.append({"site": site, "date": date, "modality": modality, "interviewer": i_name})
                violations.append({"site": site, "date": date, "modality": modality, "type": "Unpaired Interviewer", "interviewer": i_name})

        for t_name in available_testers:
            subject = f"{title_abbrev(site)} | GAP: {t_name} (tester unassigned)"
            events.append({
                "Subject": subject, "Start Date": date, "Start Time": "", "End Date": date, "End Time": "",
                "All Day Event": "True", "Description": "Tester not assigned.", "Location": site
            })
            gaps.append({"site": site, "date": date, "modality": modality, "tester": t_name})

        for s_name in solos:
            subject = f"{title_abbrev(site)} | SOLO: {s_name}"
            events.append({
                "Subject": subject, "Start Date": date, "Start Time": "", "End Date": date, "End Time": "",
                "All Day Event": "True", "Description": f"Solo provider working {modality}.", "Location": site
            })

    return pd.DataFrame(events), pd.DataFrame(violations), pd.DataFrame(gaps), provider_shift_counts, site_shift_counts

# -------------------- UI --------------------
st.title("Stonebridge Scheduler – Streamlit (Deputy Auto‑Mapper)")
st.caption("Upload Deputy roster (CSV/XLSX). The app auto‑maps headers like Location/Employee/Start Date to site/provider/date, infers modality, and outputs Google Calendar all‑day CSV with SA abbreviation.")

c1, c2 = st.columns(2)
with c1:
    roster_file = st.file_uploader("1) Upload Deputy roster (CSV or XLSX)", type=["csv","xlsx","xls"])
with c2:
    master_file = st.file_uploader("Optional: Provider Master (CSV/XLSX: provider, language, is_spanish, preferred_tester)", type=["csv","xlsx","xls"])

if st.button("Run pairings", type="primary", disabled=not roster_file) and roster_file:
    try:
        roster_raw = norm_col(load_tabular(roster_file))
        master_df = norm_col(load_tabular(master_file)) if master_file else None
        lang_map, pref_map = build_master_maps(master_df)

        events_df, violations_df, gaps_df, cnt_by_provider, cnt_by_site = generate_pairings(roster_raw, lang_map, pref_map)
        csv_text = to_google_csv(events_df.to_dict(orient="records"))
        fname = f"Stonebridge_Pairings_{timestamp()}.csv"

        st.success(f"Generated {len(events_df)} calendar rows.")
        st.download_button("Download Google Calendar CSV", data=csv_text.encode("utf-8"), file_name=fname, mime="text/csv")

        st.subheader("Summary")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**Shifts per site**")
            st.dataframe(cnt_by_site.reset_index().rename(columns={"index":"site","site":"count","provider":"count"}))
        with s2:
            st.markdown("**Shifts per provider**")
            st.dataframe(cnt_by_provider.reset_index().rename(columns={"index":"provider","provider":"count","site":"count"}).sort_values("site", ascending=False))

        st.subheader("Violations")
        if not violations_df.empty:
            st.dataframe(violations_df)
        else:
            st.info("No violations detected.")

        st.subheader("Gaps")
        if not gaps_df.empty:
            st.dataframe(gaps_df)
        else:
            st.info("No gaps detected.")

    except Exception as e:
        st.error(f"Error: {e}")
