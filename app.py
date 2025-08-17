
import io
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stonebridge Scheduler – Streamlit (Deputy Column Mapper)", layout="wide")

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

def to_google_csv(df: pd.DataFrame) -> str:
    cols = ["Subject","Start Date","Start Time","End Date","End Time","All Day Event","Description","Location"]
    export = df[cols].copy()
    export["All Day Event"] = "True"
    buf = io.StringIO()
    export.to_csv(buf, index=False)
    return buf.getvalue()

def load_tabular(uploaded_file) -> pd.DataFrame:
    # Accept CSV or XLSX
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file, dtype=str)
    return pd.read_csv(uploaded_file, dtype=str)

def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def to_iso_date(val: str, fmt_hint: str = "auto") -> str:
    s = (val or "").strip()
    if not s:
        return ""
    if fmt_hint == "mdy":
        try:
            return pd.to_datetime(s, format="%m/%d/%Y", errors="coerce").strftime("%Y-%m-%d")
        except Exception:
            pass
    # auto
    try:
        return pd.to_datetime(s, errors="coerce", infer_datetime_format=True).strftime("%Y-%m-%d")
    except Exception:
        pass
    # manual MM/DD/YYYY fallback if it contains '/'
    if "/" in s:
        parts = s.split()[0].split("/")
        if len(parts) >= 3:
            mm = parts[0].zfill(2); dd = parts[1].zfill(2); yyyy = parts[2]
            if len(yyyy) == 2: yyyy = "20"+yyyy
            return f"{yyyy}-{mm}-{dd}"
    return s[:10]

SPANISH_SET = {
    "cintia martinez","liliana pizana","emma thomae","ben aguilar","cesar villarreal",
    "teresa castano","dr. alvarez-sanders","alvarez-sanders","belinda castillo","noemi martinez"
}

def get_lang(name: str) -> str:
    if not name: return "english"
    return "spanish" if any(tok in name.lower() for tok in SPANISH_SET) else "english"

def preferred_score(interviewer: str, tester: str) -> int:
    i = (interviewer or "").lower()
    t = (tester or "").lower()
    if "lakaii jones" in i and "virginia parker" in t: return 5
    if "lyn mcdonald" in i and "ed howarth" in t: return 5
    if "liliana pizana" in i and "emma thomae" in t: return 4
    # language match\n
    if get_lang(i) == get_lang(t): return 2
    return 0

def normalize_by_mapping(df: pd.DataFrame, mapping: dict, infer_modality_from_site: bool, date_hint: str):
    # mapping keys: site,date,modality,role,provider,language (values = original column names or "")
    def pick(row, key):
        col = mapping.get(key, "")
        return "" if not col else str(row.get(col, "")).strip()

    rows = []
    for _, r in df.iterrows():
        site = pick(r, "site")
        date_raw = pick(r, "date")
        date = to_iso_date(date_raw, fmt_hint=date_hint)
        modality = pick(r, "modality")
        role_guess = pick(r, "role").lower()
        provider = pick(r, "provider")
        language = (pick(r, "language") or "English").lower()

        if not modality and infer_modality_from_site:
            modality = "Telehealth" if "tele" in (site or "").lower() else "Live"

        role = role_guess
        if role not in {"interviewer","tester","solo"}:
            if any(k in role_guess for k in ["tester","lpa","psychometric"]): role = "tester"
            elif any(k in role_guess for k in ["solo","independent"]): role = "solo"
            else: role = "interviewer"

        rows.append({
            "site": site, "date": date, "modality": modality, "role": role, "provider": provider, "language": language
        })
    out = pd.DataFrame(rows)
    # filter fully specified rows
    out = out[(out["site"]!="") & (out["date"]!="") & (out["modality"]!="") & (out["role"]!="") & (out["provider"]!="")]
    return out

def generate_pairings(df_norm: pd.DataFrame):
    grouped = df_norm.groupby(["site","date","modality"], dropna=False)

    events = []
    violations = []
    gaps = []

    site_shift_counts = df_norm.groupby("site")["provider"].count()
    provider_shift_counts = df_norm.groupby("provider")["site"].count()

    for (site, date, modality), grp in grouped:
        interviewers = [r["provider"] for _, r in grp[grp["role"]=="interviewer"].iterrows()]
        testers = [r["provider"] for _, r in grp[grp["role"]=="tester"].iterrows()]
        solos = [r["provider"] for _, r in grp[grp["role"]=="solo"].iterrows()]

        available_testers = set(testers)

        for i_name in interviewers:
            best_t = None
            best_score = -1
            for t_name in list(available_testers):
                score = preferred_score(i_name, t_name)
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
                if best_score < 4 and ("lakaii jones" in i_name.lower() or "lyn mcdonald" in i_name.lower() or get_lang(i_name) == "spanish"):
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
st.title("Stonebridge Scheduler – Streamlit (Deputy Column Mapper)")
st.caption("Upload your Deputy roster (CSV/XLSX). Map your columns to the required fields, choose date format, then generate the Google Calendar all-day CSV (SA abbreviation, pairings/gaps/violations).")

roster_file = st.file_uploader("1) Upload Deputy roster (CSV or XLSX)", type=["csv","xlsx","xls"])

if roster_file:
    df_raw = norm_cols(load_tabular(roster_file))
    headers = list(df_raw.columns)

    st.subheader("2) Map your columns")
    st.caption("Choose which header corresponds to each required field. Defaults are guesses; change if they’re wrong.")
    def guess(options, candidates):
        for c in candidates:
            for o in options:
                if o.lower() == c.lower():
                    return o
        return ""

    site_col = st.selectbox("site →", options=[""] + headers, index=([""]+headers).index(guess(headers, ["Location","Site","Work Location","Venue"])) if guess(headers, ["Location","Site","Work Location","Venue"]) in headers else 0)
    date_col = st.selectbox("date →", options=[""] + headers, index=([""]+headers).index(guess(headers, ["Date","Shift Date","Start Date","Start","Day"])) if guess(headers, ["Date","Shift Date","Start Date","Start","Day"]) in headers else 0)
    modality_col = st.selectbox("modality →", options=[""] + headers, index=([""]+headers).index(guess(headers, ["Modality","Type","Category","Mode"])) if guess(headers, ["Modality","Type","Category","Mode"]) in headers else 0)
    role_col = st.selectbox("role →", options=[""] + headers, index=([""]+headers).index(guess(headers, ["Role","Area","Position","Duty","Job","Title"])) if guess(headers, ["Role","Area","Position","Duty","Job","Title"]) in headers else 0)
    provider_col = st.selectbox("provider →", options=[""] + headers, index=([""]+headers).index(guess(headers, ["Provider","Employee","Employee Name","Name","Staff"])) if guess(headers, ["Provider","Employee","Employee Name","Name","Staff"]) in headers else 0)
    language_col = st.selectbox("language (optional) →", options=[""] + headers, index=([""]+headers).index(guess(headers, ["Language","Lang"])) if guess(headers, ["Language","Lang"]) in headers else 0)

    st.subheader("3) Date format")
    date_hint = st.radio("How are your dates formatted?", options=["auto","MM/DD/YYYY (choose this if the auto guess fails)"], index=0)
    date_hint_val = "mdy" if date_hint.startswith("MM/") else "auto"

    infer_modality = st.checkbox("If modality is blank, infer Telehealth when site contains 'tele', otherwise Live", value=True)

    mapping = {"site": site_col, "date": date_col, "modality": modality_col, "role": role_col, "provider": provider_col, "language": language_col}

    st.subheader("4) Preview (first 10 rows after mapping)")
    df_norm = normalize_by_mapping(df_raw, mapping, infer_modality_from_site=infer_modality, date_hint=date_hint_val)
    st.dataframe(df_norm.head(10))

    missing_cols = [k for k in ["site","date","modality","role","provider"] if not mapping.get(k)]
    if missing_cols:
        st.error(f"Select a column for: {', '.join(missing_cols)}")
    elif df_norm.empty:
        st.error("After mapping, no valid rows were found. Adjust your mappings or date format.")
    else:
        if st.button("5) Run pairings", type="primary"):
            events_df, violations_df, gaps_df, cnt_by_provider, cnt_by_site = generate_pairings(df_norm)
            csv_text = to_google_csv(events_df)
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
            if not violations_df.empty: st.dataframe(violations_df)
            else: st.info("No violations detected.")

            st.subheader("Gaps")
            if not gaps_df.empty: st.dataframe(gaps_df)
            else: st.info("No gaps detected.")
else:
    st.info("Upload a Deputy roster to begin.")
