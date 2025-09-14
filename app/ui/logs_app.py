# import os, json, time
# from datetime import datetime
# import pandas as pd
# import streamlit as st

# st.set_page_config(page_title="Agent Logs", layout="wide")

# LOGS_PATH = os.getenv("LOGS_PATH", "./data/logs.jsonl")

# # ---- Sidebar filters
# st.sidebar.header("Filters")
# auto = st.sidebar.toggle("Auto-refresh (5s)", value=True)
# decisions = st.sidebar.multiselect(
#     "Decision type",
#     ["REPLY","ESCALATE","SKIP","DRAFT","RETRIEVE","REWRITE","VALIDATED"],
#     default=["REPLY","ESCALATE","SKIP","DRAFT","RETRIEVE","REWRITE","VALIDATED"]
# )
# search = st.sidebar.text_input("Search (subject/from/reason)")

# st.title("📬 Email Agent — Live Logs")

# def read_logs():
#     if not os.path.exists(LOGS_PATH):
#         return []
#     rows = []
#     with open(LOGS_PATH, "r", encoding="utf-8") as f:
#         for line in f:
#             try:
#                 rows.append(json.loads(line))
#             except:
#                 pass
#     return rows

# def as_df(rows):
#     if not rows: return pd.DataFrame()
#     df = pd.DataFrame(rows)
#     if "ts" in df.columns:
#         df["ts"] = pd.to_datetime(df["ts"], unit="s")
#     for col in ["from_addr","subject","decision","reason"]:
#         if col not in df.columns:
#             df[col] = ""
#     return df

# def kpis(df):
#     total = len(df)
#     replied = (df["decision"]=="REPLY").sum()
#     skipped = (df["decision"]=="SKIP").sum()
#     escal  = (df["decision"]=="ESCALATE").sum()
#     col1,col2,col3,col4 = st.columns(4)
#     col1.metric("Total events", total)
#     col2.metric("Replied", replied)
#     col3.metric("Skipped", skipped)
#     col4.metric("Escalated", escal)

# def apply_filters(df):
#     if df.empty: return df
#     df = df[df["decision"].isin(decisions)]
#     if search:
#         s = search.lower()
#         df = df[
#             df["subject"].fillna("").str.lower().str.contains(s)
#             | df["from_addr"].fillna("").str.lower().str.contains(s)
#             | df["reason"].fillna("").str.lower().str.contains(s)
#         ]
#     return df

# def message_timeline(df):
#     """
#     Group rows by message_id and show a neat timeline for last 10 messages.
#     """
#     if df.empty or "message_id" not in df: return
#     st.subheader("Details")
#     last_ids = list(df["message_id"].dropna().unique())[-10:]
#     for mid in last_ids[::-1]:
#         chunk = df[df["message_id"]==mid].sort_values("ts")
#         head = chunk.iloc[-1]  # last state
#         with st.expander(f"📩 {head.get('subject','(no subject)')}  •  {head.get('decision','')}", expanded=False):
#             st.write(f"**From:** {head.get('from_addr','')}  \n**Message ID:** `{mid}`")
#             st.write("---")
#             for _, row in chunk.iterrows():
#                 t = row["ts"]
#                 dec = str(row.get("decision",""))
#                 rsn = str(row.get("reason",""))
#                 st.markdown(f"**{t} — {dec}**  \n{rsn}")
#                 # context/draft previews
#                 ctx = row.get("context_preview")
#                 if isinstance(ctx, list) and ctx:
#                     st.caption("Context preview:")
#                     for c in ctx[:2]:
#                         st.code(c, language="text")
#                 draft = row.get("draft_preview")
#                 if isinstance(draft, str) and draft:
#                     st.caption("Draft preview:")
#                     st.code(draft, language="markdown")

# while True:
#     rows = read_logs()
#     df = as_df(rows)
#     kpis(df)

#     # main table
#     dfv = apply_filters(df)
#     if dfv.empty:
#         st.info("No logs matching filters yet.")
#     else:
#         st.dataframe(
#             dfv[["ts","from_addr","subject","decision","reason"]].sort_values("ts", ascending=False),
#             use_container_width=True,
#             height=420,
#         )
#     message_timeline(df)

#     if not auto: break
#     time.sleep(5)
#     st.rerun()













import os, json, time, html, shutil, tempfile
from datetime import datetime, date, timedelta
import pandas as pd
import streamlit as st

# -------------------- PAGE / SETTINGS --------------------
st.set_page_config(page_title="Agent Logs", layout="wide")
LOGS_PATH  = os.getenv("LOGS_PATH", "./data/logs.jsonl")
BACKUP_DIR = os.getenv("LOGS_BACKUP_DIR", "./data/backups")
TABLE_LIMIT = 10  # show only the most recent 10 monitoring logs

# -------------------- THEME (Clean Light, High Contrast) --------------------
st.markdown("""
<style>
:root{
  --bg:#f7f8fb;
  --panel:#ffffff;
  --ink:#0b1220;
  --muted:#6b7280;
  --line:#e5e7eb;
  --brand:#0ea5e9;         /* cyan/sky accent */
  --brand-soft:#f0f9ff;
  --ok:#16a34a;   --ok-soft:#ecfdf5;
  --warn:#b45309; --warn-soft:#fffbeb;
  --skip:#334155; --skip-soft:#f1f5f9;
  --info:#2563eb; --info-soft:#eff6ff;
  --violet:#7c3aed; --violet-soft:#f5f3ff;
}

html, body, .block-container { background: var(--bg); color: var(--ink); }
.block-container { padding-top: 1rem; }

/* Title */
.header {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.header h1 { margin: 0; font-size: 22px; }

/* Sidebar redesign */
section[data-testid="stSidebar"] > div {
  background: var(--panel);
  border-right: 1px solid var(--line);
}
.sidebar-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 12px;
}
.sidebar-title {
  font-weight: 800; font-size: 0.95rem; margin-bottom: 8px;
}

/* KPIs */
.kpi-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.kpi {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
}
.kpi small { color: var(--muted); font-weight:700; letter-spacing:.02em; }
.kpi h1 { margin: 2px 0 0; font-size: 30px; }

/* Cards */
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 12px;
}

/* Table */
.table-wrap { overflow:auto; border-radius:10px; border:1px solid var(--line); }
.table { width:100%; border-collapse:separate; border-spacing:0; font-size: 14px; }
.table th, .table td { padding:10px; border-bottom:1px solid var(--line); vertical-align:top; }
.table th { background:#fafafa; text-align:left; position:sticky; top:0; z-index:1; }
.table tr:nth-child(even) td { background:#fcfdff; }
.table tr:hover td { background:#f5fbff; }

/* Badges */
.badge { padding:4px 8px; border-radius:8px; font-weight:800; font-size:12px; border:1px solid transparent; }
.badge-REPLY{ background:var(--ok-soft); color:var(--ok); border-color:#bbf7d0; }
.badge-ESCALATE{ background:var(--warn-soft); color:var(--warn); border-color:#fde68a; }
.badge-SKIP{ background:var(--skip-soft); color:var(--skip); border-color:#cbd5e1; }
.badge-DRAFT{ background:var(--info-soft); color:var(--info); border-color:#dbeafe; }
.badge-REWRITE{ background:var(--violet-soft); color:var(--violet); border-color:#ddd6fe; }
.badge-RETRIEVE{ background:var(--brand-soft); color:var(--brand); border-color:#bae6fd; }
.badge-VALIDATED{ background:#eef2ff; color:#4f46e5; border-color:#c7d2fe; }

/* Threads */
.thread {
  border: 1px dashed var(--line);
  border-radius: 10px;
  padding: 10px;
  margin: 8px 0;
  background: #fff;
}
.thread h4 { margin:0 0 6px 0; font-size: 15px; }
.caption { color: var(--muted); font-size: 12px; }
.hr { height:1px; background: var(--line); border:0; margin:10px 0; }

/* Inputs */
.stTextInput input, .stDateInput input {
  background:#fff; border:1px solid var(--line); border-radius:10px; color:var(--ink);
}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='header'><h1>📮 Agent Logs (Recent)</h1></div>", unsafe_allow_html=True)

# -------------------- SIDEBAR (clean layout) --------------------
with st.sidebar:
    st.markdown("<div class='sidebar-card'><div class='sidebar-title'>Auto / Search</div>", unsafe_allow_html=True)
    auto = st.toggle("Auto refresh (every 5s)", value=True)
    search = st.text_input("Quick search", help="Matches subject / from / reason")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='sidebar-card'><div class='sidebar-title'>Decision Filter</div>", unsafe_allow_html=True)
    decisions = st.multiselect(
        label="Show decisions",
        options=["REPLY","ESCALATE","SKIP","DRAFT","REWRITE","RETRIEVE","VALIDATED"],
        default=["REPLY","ESCALATE","SKIP","DRAFT","REWRITE","RETRIEVE","VALIDATED"]
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='sidebar-card'><div class='sidebar-title'>Maintenance</div>", unsafe_allow_html=True)
    cutoff_date = st.date_input(
        "Delete entries before",
        value=date.today() - timedelta(days=7),
        help="Entries on/after this date are kept."
    )
    confirm_phrase = st.text_input("Type DELETE to confirm", value="")
    do_backup = st.checkbox("Backup to /data/backups", value=True)
    del_clicked = st.button("Delete older logs", type="secondary")
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------- HELPERS --------------------
def ensure_dirs():
    os.makedirs(os.path.dirname(LOGS_PATH), exist_ok=True)
    if do_backup:
        os.makedirs(BACKUP_DIR, exist_ok=True)

def read_logs():
    if not os.path.exists(LOGS_PATH): return []
    rows=[]
    with open(LOGS_PATH,"r",encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows

def to_df(rows):
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], unit="s", errors="coerce")
    else:
        df["ts"] = pd.NaT
    for c in ["from_addr","subject","decision","reason","message_id"]:
        if c not in df: df[c] = ""
    df[["from_addr","subject","decision","reason","message_id"]] = \
        df[["from_addr","subject","decision","reason","message_id"]].fillna("")
    return df

def decorate_badge(dec):
    dec = html.escape(str(dec or ""))
    return f"<span class='badge badge-{dec}'>{dec}</span>"

def filtered(df, decisions, search):
    if df.empty: return df
    if decisions:
        df = df[df["decision"].isin(decisions)]
    if search:
        s = search.lower()
        df = df[
            df["subject"].fillna("").str.lower().str.contains(s)
            | df["from_addr"].fillna("").str.lower().str.contains(s)
            | df["reason"].fillna("").str.lower().str.contains(s)
        ]
    return df

def render_kpis(df):
    total   = len(df)
    replied = int((df["decision"]=="REPLY").sum())
    skipped = int((df["decision"]=="SKIP").sum())
    escal   = int((df["decision"]=="ESCALATE").sum())
    st.markdown("<div class='kpi-grid'>", unsafe_allow_html=True)
    for label, val in [("Total", total), ("Replied", replied), ("Skipped", skipped), ("Escalated", escal)]:
        st.markdown(f"<div class='kpi'><small>{label}</small><h1>{val}</h1></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def render_table(df):
    if df.empty:
        st.info("No logs match your filters yet.")
        return
    # Sort newest first, then take only the most recent N
    dfv = df[["ts","from_addr","subject","decision","reason"]].sort_values("ts", ascending=False).copy()
    dfv = dfv.fillna("").head(TABLE_LIMIT)

    for col in ["from_addr","subject","reason"]:
        dfv[col] = dfv[col].astype(str).map(html.escape)
    dfv["decision"] = dfv["decision"].astype(str).map(lambda x: f"<span class='badge badge-{html.escape(x)}'>{html.escape(x)}</span>")

    headers = "<tr>" + "".join(f"<th>{h}</th>" for h in ["Time","From","Subject","Decision","Reason"]) + "</tr>"
    rows = []
    for _, r in dfv.iterrows():
        cells = {
            "ts": r["ts"] if pd.notna(r["ts"]) else "",
            "from_addr": r["from_addr"],
            "subject": r["subject"],
            "decision": r["decision"],
            "reason": r["reason"],
        }
        rows.append("<tr>" + "".join(
            f"<td>{cells[c]}</td>" for c in ["ts","from_addr","subject","decision","reason"]
        ) + "</tr>")
    st.markdown("<div class='table-wrap card'><table class='table'>" + headers + "".join(rows) + "</table></div>", unsafe_allow_html=True)
    st.caption(f"Showing the most recent {TABLE_LIMIT} events.")

def render_timeline(df):
    if df.empty or "message_id" not in df: return
    st.subheader("Recent Threads (last 10)")
    mids = list(df["message_id"].fillna("").replace("", pd.NA).dropna().unique())
    if not mids:
        st.caption("No message threads to display.")
        return
    for mid in mids[-10:][::-1]:
        chunk = df[df["message_id"]==mid].sort_values("ts")
        if chunk.empty:
            continue
        head  = chunk.iloc[-1]
        title = html.escape(str(head.get("subject","(no subject)")))
        dec   = str(head.get("decision",""))
        st.markdown(f"<div class='thread'><h4>{title} {decorate_badge(dec)}</h4>", unsafe_allow_html=True)
        st.markdown(f"<div class='caption'>From: {html.escape(str(head.get('from_addr','')))} • ID: {html.escape(str(mid))}</div>", unsafe_allow_html=True)
        st.markdown("<div class='hr'></div>", unsafe_allow_html=True)
        for _,row in chunk.iterrows():
            when = row['ts'] if pd.notna(row['ts']) else ""
            d    = html.escape(str(row.get('decision','')))
            st.markdown(f"**{when} — {d}**")
            if row.get("reason"): st.write(str(row["reason"]))
            if isinstance(row.get("context_preview"), list):
                for c in row["context_preview"][:2]:
                    st.code(c, language="text")
            if row.get("draft_preview"):
                st.code(row["draft_preview"], language="markdown")
        st.markdown("</div>", unsafe_allow_html=True)

def safe_write_lines(lines):
    """Atomic rewrite with optional backup."""
    ensure_dirs()
    dirpath = os.path.dirname(LOGS_PATH) or "."
    fd, tmp_path = tempfile.mkstemp(prefix="logs_", suffix=".jsonl", dir=dirpath, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            for line in lines:
                tmp.write(line.rstrip("\n") + "\n")
        if do_backup and os.path.exists(LOGS_PATH):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(BACKUP_DIR, f"logs_backup_{stamp}.jsonl")
            shutil.copy2(LOGS_PATH, backup_file)
        shutil.move(tmp_path, LOGS_PATH)
        return True, None
    except Exception as e:
        try: os.remove(tmp_path)
        except Exception: pass
        return False, str(e)

def delete_before(cutoff_dt: datetime):
    if not os.path.exists(LOGS_PATH):
        return 0, 0, "No log file found."
    removed, kept = 0, 0
    new_lines = []
    with open(LOGS_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            try:
                obj = json.loads(line)
                ts = obj.get("ts", None)
                if ts is None:
                    kept += 1; new_lines.append(line)
                else:
                    ts_dt = pd.to_datetime(ts, unit="s", errors="coerce")
                    if pd.isna(ts_dt):
                        kept += 1; new_lines.append(line)
                    else:
                        if ts_dt.to_pydatetime() < cutoff_dt:
                            removed += 1
                        else:
                            kept += 1; new_lines.append(line)
            except Exception:
                kept += 1; new_lines.append(line)
    ok, err = safe_write_lines(new_lines)
    if not ok: return removed, kept, f"Write failed: {err}"
    return removed, kept, None

# -------------------- MAIN --------------------
def main():
    # Handle deletion first so UI reflects new state immediately
    if del_clicked:
        if confirm_phrase.strip().upper() != "DELETE":
            st.error("Please type DELETE to confirm.")
        else:
            cut = datetime.combine(cutoff_date, datetime.min.time())
            removed, kept, err = delete_before(cut)
            if err: st.error(f"Deletion error: {err}")
            else:   st.success(f"Deleted {removed} old log(s). Kept {kept}.")

    rows = read_logs()
    df   = to_df(rows)

    # KPIs
    render_kpis(df)

    # Table (limited to recent 10)
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    dfv = filtered(df, decisions, search)
    render_table(dfv)
    st.markdown("</div>", unsafe_allow_html=True)

    # Timeline (already shows last 10 threads)
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    render_timeline(dfv)
    st.markdown("</div>", unsafe_allow_html=True)

    # Auto-refresh
    if auto:
        time.sleep(5)
        st.rerun()

if __name__ == "__main__":
    main()

