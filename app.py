"""NoVa LeadScore — Streamlit App (Wiring Layer).

Upload CSV/Excel → AI scores leads → Dashboard + Download.
"""

import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import get_config
from core.detector import detect_leads
from core.scorer import score_leads
from validate import validate_dataframe

# === PAGE CONFIG ===
st.set_page_config(
    page_title="NoVa LeadScore — AI Lead Scoring",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# === CUSTOM THEME (dark, professional) ===
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');

:root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --card: #1a1a2e;
    --border: rgba(139, 92, 246, 0.2);
    --text1: #e8e4df;
    --text2: #8a8580;
    --accent: #8b5cf6;
    --hot: #ef4444;
    --warm: #f59e0b;
    --cold: #6b7280;
    --success: #10b981;
}

.stApp { background: var(--bg) !important; }

/* Header */
.app-header {
    text-align: center;
    padding: 48px 0 32px;
    font-family: 'Plus Jakarta Sans', sans-serif;
}
.app-header h1 {
    font-size: 2.4rem;
    font-weight: 800;
    background: linear-gradient(135deg, #8b5cf6, #f43f5e);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}
.app-header p {
    color: var(--text2);
    font-size: 1rem;
    font-family: 'Inter', sans-serif;
}

/* KPI Cards */
.kpi-row { display: flex; gap: 16px; margin: 24px 0; }
.kpi-card {
    flex: 1;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(139, 92, 246, 0.15);
}
.kpi-value {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: var(--text1);
}
.kpi-label {
    font-size: 0.78rem;
    color: var(--text2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 4px;
}
.kpi-hot .kpi-value { color: var(--hot); }
.kpi-warm .kpi-value { color: var(--warm); }
.kpi-cold .kpi-value { color: var(--cold); }
.kpi-avg .kpi-value { color: var(--accent); }

/* Upload zone */
.upload-zone {
    background: var(--surface);
    border: 2px dashed var(--border);
    border-radius: 16px;
    padding: 48px;
    text-align: center;
    margin: 24px auto;
    max-width: 640px;
    transition: border-color 0.3s;
}
.upload-zone:hover { border-color: var(--accent); }
.upload-icon { font-size: 2.5rem; margin-bottom: 12px; }
.upload-text { color: var(--text2); font-size: 0.9rem; }

/* Priority badges */
.badge-hot { background: rgba(239,68,68,0.15); color: #ef4444; padding: 2px 10px; border-radius: 100px; font-size: 0.78rem; font-weight: 600; }
.badge-warm { background: rgba(245,158,11,0.15); color: #f59e0b; padding: 2px 10px; border-radius: 100px; font-size: 0.78rem; font-weight: 600; }
.badge-cold { background: rgba(107,114,128,0.15); color: #6b7280; padding: 2px 10px; border-radius: 100px; font-size: 0.78rem; font-weight: 600; }

/* Powered by */
.powered-by {
    text-align: center;
    padding: 32px 0;
    color: var(--text2);
    font-size: 0.78rem;
}
.powered-by a { color: var(--accent); text-decoration: none; }

/* Demo banner */
.demo-banner {
    background: linear-gradient(135deg, rgba(139,92,246,0.08), rgba(244,63,94,0.08));
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 24px;
    text-align: center;
    margin: 16px 0;
    font-size: 0.85rem;
    color: var(--text2);
}
.demo-banner strong { color: var(--accent); }

/* Hide Streamlit defaults */
#MainMenu, header, footer { visibility: hidden; }
.stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)


# === HEADER ===
st.markdown("""
<div class="app-header">
    <h1>NoVa LeadScore</h1>
    <p>AI-powered lead scoring — upload your list, get instant insights</p>
</div>
""", unsafe_allow_html=True)

# === DEMO NOTICE (Streamlit Cloud) ===
config = get_config()
if not config.llm_api_key:
    st.markdown("""
    <div class="demo-banner">
        <strong>Demo Mode</strong> — AI scoring uses rule-based fallback. Add your API key for full AI analysis.
    </div>
    """, unsafe_allow_html=True)

# === INIT SESSION STATE ===
if "score_result" not in st.session_state:
    st.session_state.score_result = None
if "df_original" not in st.session_state:
    st.session_state.df_original = None


# === UPLOAD ZONE ===
st.markdown("""
<div class="upload-zone">
    <div class="upload-icon">📊</div>
    <div class="upload-text">Upload your lead list (CSV or Excel)</div>
</div>
""", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Upload CSV or Excel",
    type=["csv", "xlsx", "xls"],
    label_visibility="collapsed",
)


def run_scoring(df: pd.DataFrame, filename: str):
    """Execute the scoring pipeline."""
    # Detect fields
    with st.status("Analyzing your data...", expanded=True) as status:
        st.write("🔍 Detecting field types and mapping...")
        profile = detect_leads(df, filename)

        st.write(f"✅ Found {profile.total_leads} leads, {len(profile.fields)} columns")
        st.write(f"📋 Mapped: {', '.join(f'{k}={v}' for k, v in profile.field_mapping.items())}")
        st.write(f"📊 Data quality: {profile.quality_score}/100")

        # Score
        st.write("🤖 Scoring leads with AI..." if config.llm_api_key else "📐 Scoring with rule-based engine...")
        progress = st.progress(0)

        result = score_leads(
            df=df,
            profile=profile,
            config=config,
            progress_callback=lambda p: progress.progress(p),
        )

        status.update(label="Scoring complete!", state="complete")

    st.session_state.score_result = result
    st.session_state.df_original = df


# === PROCESS UPLOAD ===
if uploaded:
    try:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded, engine="openpyxl")

        ok, errs = validate_dataframe(df, config.max_leads)
        if not ok:
            for e in errs:
                st.error(e)
        else:
            # Show preview
            with st.expander(f"📋 Preview: {uploaded.name} ({len(df)} leads, {len(df.columns)} columns)", expanded=False):
                st.dataframe(df.head(10), use_container_width=True)

            if st.button("🎯 Score My Leads", type="primary", use_container_width=True):
                run_scoring(df, uploaded.name)

    except Exception as e:
        st.error(f"Could not read file: {e}")


# === RESULTS DASHBOARD ===
if st.session_state.score_result:
    result = st.session_state.score_result
    s = result.summary

    st.markdown("---")

    # KPI Row
    st.markdown(f"""
    <div class="kpi-row">
        <div class="kpi-card"><div class="kpi-value">{s['total']}</div><div class="kpi-label">Total Leads</div></div>
        <div class="kpi-card kpi-avg"><div class="kpi-value">{s['avg_score']}</div><div class="kpi-label">Avg Score</div></div>
        <div class="kpi-card kpi-hot"><div class="kpi-value">{s['hot']}</div><div class="kpi-label">Hot</div></div>
        <div class="kpi-card kpi-warm"><div class="kpi-value">{s['warm']}</div><div class="kpi-label">Warm</div></div>
        <div class="kpi-card kpi-cold"><div class="kpi-value">{s['cold']}</div><div class="kpi-label">Cold</div></div>
    </div>
    """, unsafe_allow_html=True)

    # AI/Fallback indicator
    if not result.ai_used:
        st.info("📐 Scored using rule-based engine (AI unavailable)")
    elif result.fallback_used:
        st.warning("⚡ Scored using fallback AI provider")

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        # Priority distribution
        priority_data = pd.DataFrame({
            "Priority": ["Hot", "Warm", "Cold"],
            "Count": [s["hot"], s["warm"], s["cold"]],
        })
        fig = px.pie(
            priority_data, names="Priority", values="Count",
            color="Priority",
            color_discrete_map={"Hot": "#ef4444", "Warm": "#f59e0b", "Cold": "#6b7280"},
            hole=0.4,
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8a8580"),
            showlegend=True,
            margin=dict(t=30, b=30, l=30, r=30),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Score distribution histogram
        score_df = pd.DataFrame({
            "Score": [sl.score for sl in result.scored_leads],
        })
        fig2 = px.histogram(
            score_df, x="Score", nbins=10,
            color_discrete_sequence=["#8b5cf6"],
        )
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8a8580"),
            xaxis=dict(title="Score", gridcolor="rgba(139,92,246,0.1)"),
            yaxis=dict(title="Count", gridcolor="rgba(139,92,246,0.1)"),
            margin=dict(t=30, b=30, l=30, r=30),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Scored leads table
    st.subheader("Scored Leads")

    # Build display DataFrame
    df_orig = st.session_state.df_original
    scored_data = []
    for sl in result.scored_leads:
        row_data = {"Score": sl.score, "Priority": sl.priority, "Reason": sl.reason}
        if sl.row_index < len(df_orig):
            for col in df_orig.columns[:6]:  # first 6 original columns
                row_data[col] = df_orig.iloc[sl.row_index][col]
        scored_data.append(row_data)

    df_scored = pd.DataFrame(scored_data)

    # Filter by priority
    filter_priority = st.segmented_control(
        "Filter", options=["All", "Hot", "Warm", "Cold"], default="All"
    )
    if filter_priority and filter_priority != "All":
        df_scored = df_scored[df_scored["Priority"] == filter_priority]

    st.dataframe(
        df_scored.style.apply(
            lambda row: [
                "background-color: rgba(239,68,68,0.1)" if row["Priority"] == "Hot"
                else "background-color: rgba(245,158,11,0.1)" if row["Priority"] == "Warm"
                else "background-color: rgba(107,114,128,0.1)"
            ] * len(row), axis=1
        ),
        use_container_width=True,
        height=400,
    )

    # Download section
    st.markdown("---")
    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        # CSV download
        export_data = []
        for sl in result.scored_leads:
            row = {}
            if sl.row_index < len(df_orig):
                row = df_orig.iloc[sl.row_index].to_dict()
            row["LeadScore"] = sl.score
            row["Priority"] = sl.priority
            row["AI_Reason"] = sl.reason
            row["Signals"] = "; ".join(sl.signals)
            export_data.append(row)

        export_df = pd.DataFrame(export_data)
        csv_buffer = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Scored CSV",
            data=csv_buffer,
            file_name=f"leadscore_{result.lead_profile.filename}",
            mime="text/csv",
            use_container_width=True,
        )

    with col_dl2:
        # Excel download
        excel_buffer = io.BytesIO()
        export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        st.download_button(
            "📥 Download Scored Excel",
            data=excel_buffer.getvalue(),
            file_name=f"leadscore_{Path(result.lead_profile.filename).stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# === FOOTER ===
st.markdown("""
<div class="powered-by">
    Built with AI by <a href="https://novasentio.com" target="_blank">NoVaSentio</a> ·
    <a href="https://github.com/quoctri-dev" target="_blank">GitHub</a>
</div>
""", unsafe_allow_html=True)
