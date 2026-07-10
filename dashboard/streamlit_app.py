import os
import sys
import streamlit as st
import pandas as pd
import requests
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.postgres_bronze import SessionLocal
from storage.postgres_models import BronzeDocument, Document

# ── Page Configuration ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Document Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Session State Initialisation ───────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Reset & Base ── */
  :root {
    --bg:            #09090B;
    --bg-subtle:     #18181B;
    --card-bg:       #18181B;
    --card-border:   #27272A;
    --card-hover:    #27272A;
    --primary:       #FAFAFA;
    --primary-hover: #E4E4E7;
    --accent:        #6366F1;
    --accent-hover:  #818CF8;
    --success:       #22C55E;
    --warning:       #EAB308;
    --error:         #EF4444;
    --text-primary:  #FAFAFA;
    --text-secondary:#D4D4D8;
    --text-muted:    #71717A;
    --border:        #27272A;
    --border-strong: #3F3F46;
  }

  html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    background-color: var(--bg) !important;
    color: var(--text-primary) !important;
    -webkit-font-smoothing: antialiased;
  }

  [data-testid="stAppViewContainer"] { background-color: var(--bg) !important; }
  [data-testid="stHeader"] { background-color: var(--bg) !important; }

  .main .block-container {
    background-color: var(--bg);
    padding: 2rem 2.5rem 4rem 2.5rem;
    max-width: 1100px;
  }

  /* ── Sidebar ── */
  section[data-testid="stSidebar"] {
    background-color: var(--bg-subtle) !important;
    border-right: 1px solid var(--border) !important;
  }
  section[data-testid="stSidebar"] .block-container { padding: 1.5rem 1.25rem; }
  section[data-testid="stSidebar"] * { color: var(--text-primary) !important; }

  /* ── Hide default Streamlit chrome ── */
  #MainMenu, footer { visibility: hidden; }
  .stDeployButton { display: none !important; }

  /* ── Typography ── */
  h1, h2, h3, h4 {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    line-height: 1.4 !important;
  }

  /* ── Inputs ── */
  .stTextInput > div > div > input {
    background-color: var(--bg-subtle) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 6px !important;
    color: var(--text-primary) !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
    transition: border-color 150ms ease;
  }
  .stTextInput > div > div > input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
  }
  .stTextInput > div > div > input::placeholder { color: var(--text-muted) !important; }
  .stTextInput > label {
    color: var(--text-muted) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* ── Buttons ── */
  .stButton > button {
    background-color: var(--bg-subtle) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 6px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 6px 16px !important;
    transition: all 150ms ease !important;
  }
  .stButton > button:hover {
    border-color: var(--text-primary) !important;
    background-color: var(--card-hover) !important;
  }

  /* ── File Uploader ── */
  [data-testid="stFileUploader"] {
    background-color: var(--bg-subtle) !important;
    border: 1px dashed var(--border-strong) !important;
    border-radius: 6px !important;
    padding: 16px !important;
  }

  /* ── Expanders ── */
  .streamlit-expanderHeader {
    background-color: var(--bg-subtle) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text-secondary) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
  }
  .streamlit-expanderContent {
    background-color: var(--bg) !important;
    border: 1px solid var(--border) !important;
    border-top: none !important;
    border-radius: 0 0 6px 6px !important;
    padding: 16px !important;
    color: var(--text-secondary) !important;
    font-size: 13px !important;
    line-height: 1.6 !important;
  }

  /* ── Alert boxes ── */
  .stAlert { border-radius: 6px !important; font-size: 13px !important; }

  /* ── Divider ── */
  hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 20px 0 !important; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: var(--bg-subtle); }
  ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 3px; }

  /* ── Spinner ── */
  .stSpinner > div { color: var(--text-muted) !important; }

  /* ── Code blocks ── */
  code, pre {
    background-color: var(--bg-subtle) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: #93C5FD !important;
    font-size: 13px !important;
  }

  /* Auth screen — hide sidebar */
  .auth-mode section[data-testid="stSidebar"] { display: none !important; }
  .auth-mode [data-testid="stSidebarCollapsedControl"] { display: none !important; }

  /* ════════════════════════════════════════════════
     LOADING OVERLAY
     ════════════════════════════════════════════════ */
  .loading-overlay {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: rgba(9,9,11,0.92);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }
  .loading-box {
    text-align: center;
    padding: 40px;
  }
  .loading-spinner {
    width: 44px; height: 44px;
    border: 3px solid var(--border-strong);
    border-top: 3px solid var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 24px;
  }
  @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
  .loading-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 6px 0;
  }
  .loading-sub {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }
  .loading-steps {
    margin-top: 28px;
    text-align: left;
    display: inline-block;
  }
  .loading-step {
    font-size: 13px;
    color: var(--text-muted);
    padding: 5px 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .loading-step .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--border-strong);
    flex-shrink: 0;
  }

  /* ════════════════════════════════════════════════
     CHAT / QUERY MAIN PANEL
     ════════════════════════════════════════════════ */
  .chat-header {
    padding: 0 0 20px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 28px;
  }
  .chat-title {
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary) !important;
    letter-spacing: -0.02em;
    margin: 0 0 4px 0;
  }
  .chat-subtitle {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
    font-weight: 400;
  }

  /* ── Custom Components (Reused) ── */
  .intel-card {
    background-color: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    transition: background-color 200ms ease;
  }
  .intel-card:hover { background-color: var(--card-hover); }
  .intel-card .label {
    font-size: 11px; font-weight: 600; color: var(--text-muted);
    letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 6px;
  }
  .intel-card .value {
    font-size: 17px; font-weight: 600; color: var(--text-primary); margin: 0;
  }

  .answer-block {
    background-color: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 24px;
    margin-top: 24px;
  }
  .answer-block .section-label {
    font-size: 11px; font-weight: 600; color: var(--text-muted);
    letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 14px;
  }
  .answer-block .answer-text {
    font-size: 15px; color: var(--text-primary); line-height: 1.7; white-space: pre-wrap;
  }

  .abstain-block {
    background-color: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.25);
    border-radius: 8px;
    padding: 16px 20px;
    margin-top: 24px;
  }
  .abstain-block .label {
    font-size: 12px; font-weight: 600; color: var(--error);
    letter-spacing: 0.04em; margin-bottom: 6px;
  }
  .abstain-block .msg { font-size: 14px; color: var(--text-secondary); }

  .warn-block {
    background-color: rgba(245,158,11,0.08);
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: 8px;
    padding: 14px 18px;
    margin-top: 12px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .badge {
    display: inline-block;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.05em;
    padding: 3px 10px;
    border-radius: 4px;
    text-transform: uppercase;
  }
  .badge-blue   { background: rgba(59,130,246,0.15);  color: #60A5FA; }
  .badge-purple { background: rgba(139,92,246,0.15);  color: #A78BFA; }
  .badge-green  { background: rgba(16,185,129,0.15);  color: #34D399; }
  .badge-amber  { background: rgba(245,158,11,0.15);  color: #FCD34D; }
  .badge-red    { background: rgba(239,68,68,0.15);   color: #F87171; }
  .badge-gray   { background: rgba(107,114,128,0.15); color: #9CA3AF; }
  .badge-teal   { background: rgba(20,184,166,0.15);  color: #2DD4BF; }

  .doc-card {
    background-color: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: background-color 200ms ease;
  }
  .doc-card:hover { background-color: var(--card-hover); }
  .doc-card .doc-name {
    font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;
  }
  .doc-card .doc-meta { font-size: 12px; color: var(--text-muted); }

  .section-label {
    font-size: 11px; font-weight: 600; color: var(--text-muted);
    letter-spacing: 0.06em; text-transform: uppercase;
    margin-bottom: 16px; margin-top: 28px;
  }

  .sidebar-section-title {
    font-size: 11px; font-weight: 600; color: var(--text-muted);
    letter-spacing: 0.06em; text-transform: uppercase;
    margin-bottom: 12px; margin-top: 20px;
  }

  .sidebar-stat {
    font-size: 13px; color: var(--text-secondary);
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
  }
  .sidebar-stat:last-child { border-bottom: none; }

  /* ── Responsive ── */
  @media (max-width: 768px) {
    .main .block-container { padding: 1rem 1rem 3rem 1rem; }
    .auth-card { padding: 32px 24px; }
  }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:55432/document_platform")
engine = create_engine(DATABASE_URL)

@st.cache_data(ttl=10)
def fetch_pipeline_metrics(tenant_id: str):
    with engine.connect() as conn:
        df_docs = pd.read_sql(
            text("SELECT document_id, status, source_type FROM gold.dim_document WHERE is_current = true AND tenant_id = :tenant_id"),
            conn, params={"tenant_id": tenant_id}
        )
        df_processing = pd.read_sql(
            text("SELECT document_id, ocr_confidence, page_count, processing_timestamp FROM gold.fact_document_processing WHERE tenant_id = :tenant_id"),
            conn, params={"tenant_id": tenant_id}
        )
        df_runs = pd.read_sql(
            text("SELECT run_id, execution_date, status FROM gold.dim_pipeline_run WHERE tenant_id = :tenant_id"),
            conn, params={"tenant_id": tenant_id}
        )
    return df_docs, df_processing, df_runs

def format_local_time(series):
    """Convert UTC timestamps to IST (Asia/Kolkata) in human-readable format."""
    try:
        dt_series = pd.to_datetime(series, utc=True)
        formatted = dt_series.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %I:%M:%S %p")
        return formatted.fillna("-")
    except Exception:
        return series

def badge(text_val: str, color: str = "gray") -> str:
    return f'<span class="badge badge-{color}">{text_val}</span>'

def confidence_color(level: str) -> str:
    return {"high": "green", "medium": "amber", "low": "amber", "none": "red"}.get(level, "gray")

def qtype_color(qt: str) -> str:
    return {"aggregation": "blue", "comparison": "purple", "table_lookup": "teal",
            "descriptive": "gray", "synthesis": "teal"}.get(qt, "gray")

def routing_color(path: str) -> str:
    return "blue" if path == "structured" else "purple"


# ══════════════════════════════════════════════════════════════════════════════
#  AUTHENTICATION GATE
# ══════════════════════════════════════════════════════════════════════════════

if not st.session_state.authenticated:
    # Hide sidebar on the auth screen
    st.markdown('<script>document.querySelector("html").classList.add("auth-mode")</script>', unsafe_allow_html=True)
    st.markdown('<style>.auth-mode section[data-testid="stSidebar"]{display:none!important}.auth-mode [data-testid="stSidebarCollapsedControl"]{display:none!important}</style>', unsafe_allow_html=True)

    # Vertical spacer to push content towards center
    for _ in range(6):
        st.write("")

    # Centered column layout
    _, col_form, _ = st.columns([1.5, 1, 1.5])

    with col_form:
        st.markdown("#### Document Intelligence Platform")
        st.caption("Sign in with your user ID to access your document corpus.")
        st.write("")

        user_id_input = st.text_input(
            "User ID",
            placeholder="Enter your user ID",
            key="auth_user_input"
        )

        st.write("")

        if st.button("Sign In", use_container_width=True, key="auth_continue", type="primary"):
            if user_id_input and user_id_input.strip():
                st.session_state.authenticated = True
                st.session_state.user_id = user_id_input.strip()
                st.rerun()
            else:
                st.error("Please enter a valid user ID.")

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP — Only renders if authenticated
# ══════════════════════════════════════════════════════════════════════════════

tenant_id = st.session_state.user_id

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── User Info ──
    st.markdown(f"""
    <div style="padding:16px 0 14px 0; border-bottom:1px solid var(--border);">
      <div style="font-size:11px; color:var(--text-muted); text-transform:uppercase;
           font-weight:600; letter-spacing:0.06em;">Signed in as</div>
      <div style="font-size:16px; font-weight:600; color:var(--text-primary);
           margin-top:6px;">{tenant_id}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Upload Section ──
    st.markdown('<div class="sidebar-section-title">Upload Document</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "txt", "csv", "jpg", "jpeg", "png"],
        label_visibility="collapsed",
        key="sidebar_file_uploader"
    )

    if uploaded_file is not None:
        if st.button("Upload", use_container_width=True, key="sidebar_upload_btn"):
            # Show loading overlay
            loading_ph = st.empty()
            loading_ph.markdown("""
            <div class="loading-overlay">
              <div class="loading-box">
                <div class="loading-spinner"></div>
                <div class="loading-title">Processing Document</div>
                <div class="loading-sub">This may take a moment…</div>
                <div class="loading-steps">
                  <div class="loading-step"><span class="dot" style="background:var(--accent)"></span> Uploading file</div>
                  <div class="loading-step"><span class="dot"></span> Extracting content</div>
                  <div class="loading-step"><span class="dot"></span> Quality check</div>
                  <div class="loading-step"><span class="dot"></span> Embedding</div>
                  <div class="loading-step"><span class="dot"></span> Indexing</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                headers = {"X-Tenant-ID": tenant_id}
                response = requests.post(
                    f"{os.environ.get('API_URL', 'http://127.0.0.1:8001')}/upload",
                    files=files, headers=headers, timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    doc_id = result['document_id']
                    
                    # Wait for background pipeline to complete (Quality Gate -> Embed -> dbt run)
                    import time
                    max_retries = 60  # Wait up to 2 minutes
                    pipeline_done = False
                    
                    for _ in range(max_retries):
                        # 1. Check if it failed quality gate early
                        _db_check = SessionLocal()
                        b_doc = _db_check.query(BronzeDocument).filter(BronzeDocument.document_id == doc_id).first()
                        if b_doc and b_doc.status == "failed":
                            _db_check.close()
                            pipeline_done = True
                            break
                        _db_check.close()
                        
                        # 2. Check if it reached the gold layer (means dbt run finished successfully)
                        with engine.connect() as conn:
                            res = conn.execute(
                                text("SELECT 1 FROM gold.dim_document WHERE document_id = :doc_id"), 
                                {"doc_id": doc_id}
                            ).fetchone()
                            if res:
                                pipeline_done = True
                                break
                                
                        time.sleep(2)
                        
                    loading_ph.empty()
                    
                    if pipeline_done:
                        st.success(f"Processed. Document ID: {doc_id[:8]}")
                        time.sleep(1) # Brief pause so they see the success message
                        st.rerun()
                    else:
                        st.error("Processing timed out. Please check backend logs.")
                else:
                    loading_ph.empty()
                    st.error(f"Upload failed: {response.text}")
            except Exception as ex:
                loading_ph.empty()
                st.error(f"Connection error: {ex}")
    else:
        st.markdown("""
        <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">
          PDF, TXT, CSV, JPG, PNG · Max 200 MB
        </div>
        """, unsafe_allow_html=True)

    # ── Document Status (live counts) ──
    st.markdown('<div class="sidebar-section-title" style="margin-top:28px">Documents</div>', unsafe_allow_html=True)
    try:
        _db = SessionLocal()
        _all_docs = _db.query(BronzeDocument).filter(BronzeDocument.tenant_id == tenant_id).all()
        _total = len(_all_docs)
        _curated = sum(1 for d in _all_docs if d.status == "curated")
        _failed = sum(1 for d in _all_docs if d.status == "failed")
        _pending = _total - _curated - _failed
        _db.close()
    except Exception:
        _total = _curated = _failed = _pending = 0

    st.markdown(f"""
    <div class="sidebar-stat">Total: <strong style="color:var(--text-primary)">{_total}</strong></div>
    <div class="sidebar-stat">Curated: <strong style="color:#34D399">{_curated}</strong></div>
    <div class="sidebar-stat">Failed: <strong style="color:#F87171">{_failed}</strong></div>
    <div class="sidebar-stat">Pending: <strong style="color:#FCD34D">{_pending}</strong></div>
    """, unsafe_allow_html=True)

    # ── Pipeline Metrics (expander) ──
    st.markdown('<div class="sidebar-section-title" style="margin-top:28px">Analytics</div>', unsafe_allow_html=True)

    with st.expander("Pipeline Metrics", expanded=False):
        try:
            df_docs, df_processing, df_runs = fetch_pipeline_metrics(tenant_id)
            if not df_docs.empty:
                df_merged = pd.merge(df_docs, df_processing, on="document_id", how="left")
                total_docs   = len(df_docs)
                curated_docs = len(df_docs[df_docs["status"] == "curated"])
                failed_docs  = len(df_docs[df_docs["status"] == "failed"])
                pass_rate    = (curated_docs / total_docs * 100) if total_docs > 0 else 0.0

                scanned = df_merged[df_merged["source_type"].isin(["scanned_pdf", "scanned", "image"])]
                avg_ocr = scanned["ocr_confidence"].mean() if not scanned.empty else None

                st.markdown(f"""
                <div class="sidebar-stat">Documents: <strong>{total_docs}</strong></div>
                <div class="sidebar-stat">Pass Rate: <strong>{pass_rate:.0f}%</strong></div>
                """, unsafe_allow_html=True)
                if avg_ocr is not None:
                    st.markdown(f'<div class="sidebar-stat">Avg OCR: <strong>{avg_ocr:.1f}%</strong></div>', unsafe_allow_html=True)

                # Document Telemetry table
                if not df_merged.empty and "processing_timestamp" in df_merged.columns:
                    df_merged["processing_timestamp"] = format_local_time(df_merged["processing_timestamp"])
                st.markdown('<div style="margin-top:12px; font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.06em;">Telemetry</div>', unsafe_allow_html=True)
                if not df_merged.empty:
                    st.dataframe(
                        df_merged.rename(columns={
                            "document_id": "Doc ID", "status": "Status",
                            "source_type": "Type", "ocr_confidence": "OCR",
                            "page_count": "Pages", "processing_timestamp": "Processed At"
                        }),
                        use_container_width=True, hide_index=True, height=200
                    )

                # Pipeline Runs table
                if not df_runs.empty and "execution_date" in df_runs.columns:
                    df_runs["execution_date"] = format_local_time(df_runs["execution_date"])
                st.markdown('<div style="margin-top:12px; font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.06em;">Pipeline Runs</div>', unsafe_allow_html=True)
                if not df_runs.empty:
                    st.dataframe(
                        df_runs.rename(columns={"run_id": "Run ID", "execution_date": "Date", "status": "Status"}),
                        use_container_width=True, hide_index=True, height=150
                    )
                else:
                    st.markdown('<div style="font-size:12px; color:var(--text-muted);">No runs recorded.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:12px; color:var(--text-muted);">No pipeline data yet.</div>', unsafe_allow_html=True)
        except Exception:
            st.markdown('<div style="font-size:12px; color:var(--text-muted);">Pipeline data unavailable.</div>', unsafe_allow_html=True)

    # ── Document Catalog (expander) ──
    with st.expander("Document Catalog", expanded=False):
        try:
            db_cat = SessionLocal()
            docs = db_cat.query(BronzeDocument).filter(
                BronzeDocument.tenant_id == tenant_id
            ).order_by(BronzeDocument.created_at.desc()).all()

            if not docs:
                st.markdown('<div style="font-size:12px; color:var(--text-muted);">No documents uploaded yet.</div>', unsafe_allow_html=True)
            else:
                for doc in docs:
                    fname   = doc.filename or f"Document {doc.document_id[:8]}"
                    stype   = (doc.source_type or "unknown").replace("_", " ").title()
                    purpose = getattr(doc, "document_purpose", None) or "—"
                    status  = doc.status or "unknown"
                    s_color = "green" if status == "curated" else ("red" if status == "failed" else "gray")

                    st.markdown(f"""
                    <div style="padding:8px 0; border-bottom:1px solid var(--border); font-size:13px;">
                      <div style="font-weight:600; color:var(--text-primary);">{fname}</div>
                      <div style="color:var(--text-muted); font-size:11px; margin-top:2px;">
                        {stype} · {purpose} · {badge(status, s_color)}
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("Delete", key=f"del_{doc.document_id}", help=f"Delete {fname}"):
                        with st.spinner("Deleting…"):
                            db_cat.query(Document).filter(Document.document_id == doc.document_id).delete()
                            db_cat.query(BronzeDocument).filter(BronzeDocument.document_id == doc.document_id).delete()
                            db_cat.commit()
                            try:
                                from rag import qdrant_store
                                from qdrant_client.http.models import Filter, FieldCondition, MatchValue
                                q_client = qdrant_store.get_client()
                                q_client.delete(
                                    collection_name="document_chunks",
                                    points_selector=Filter(
                                        must=[FieldCondition(key="document_id", match=MatchValue(value=doc.document_id))]
                                    )
                                )
                            except Exception:
                                pass
                            st.rerun()
            db_cat.close()
        except Exception as db_err:
            st.markdown(f'<div style="font-size:12px; color:var(--error);">Error: {db_err}</div>', unsafe_allow_html=True)

    # ── Switch User ──
    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    if st.button("Switch User", use_container_width=True, key="switch_user_btn"):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()


# ── MAIN PANEL — Chat-like Query Interface ─────────────────────────────────────
st.markdown(f"""
<div class="chat-header">
  <div class="chat-title">Query Documents</div>
  <div class="chat-subtitle">
    Ask questions about your uploaded documents · Tenant: <strong style="color:var(--text-secondary)">{tenant_id}</strong>
  </div>
</div>
""", unsafe_allow_html=True)

is_processing = _pending > 0
no_curated = _curated == 0
query_disabled = is_processing or no_curated

if is_processing:
    st.info("Documents are currently being processed. The query interface will be available once all documents are fully curated.")
elif no_curated:
    st.warning("No curated documents available. Please upload a document to begin querying.")

query = st.text_input(
    "Query",
    placeholder="Ask a question about your documents…" if not query_disabled else "Querying temporarily unavailable",
    label_visibility="collapsed",
    key="query_input",
    disabled=query_disabled
)
ask_btn = st.button("Ask", key="ask_button", disabled=query_disabled)

if ask_btn and query.strip():
    with st.status("Querying documents...", expanded=True) as status_box:
        try:
            import time
            start_time = time.time()
            from rag.query_router import route_query
            def update_status(text_msg):
                status_box.update(label=text_msg, state="running")
            result = route_query(query=query, tenant_id=tenant_id, status_callback=update_status, stream=True)
            
            end_time_routing = time.time()
            execution_time = end_time_routing - start_time
            
            answer           = result.get("answer", "")
            answer_generator = result.get("answer_generator")
            routing_path     = result["routing_path"]
            q_type           = result["query_type"]
            confidence       = result["confidence"]
            abstained        = result["abstained"]
            citations        = result.get("citations", [])
            chunks_list      = result.get("chunks", [])
            low_conf_warn    = result.get("low_confidence_warning", False)
            pandas_code      = result.get("structured_query_executed")

            st.markdown('<hr>', unsafe_allow_html=True)

            # ── Query Intelligence ──
            st.markdown('<div class="section-label">Query Intelligence</div>', unsafe_allow_html=True)
            ci1, ci2, ci3, ci4, ci5 = st.columns(5)
            with ci1:
                st.markdown(f"""<div class="intel-card">
                  <div class="label">Query Type</div>
                  <div class="value">{badge(q_type, qtype_color(q_type))}</div>
                </div>""", unsafe_allow_html=True)
            with ci2:
                st.markdown(f"""<div class="intel-card">
                  <div class="label">Routing Path</div>
                  <div class="value">{badge(routing_path, routing_color(routing_path))}</div>
                </div>""", unsafe_allow_html=True)
            with ci3:
                st.markdown(f"""<div class="intel-card">
                  <div class="label">Evidence Confidence</div>
                  <div class="value">{badge(confidence, confidence_color(confidence))}</div>
                </div>""", unsafe_allow_html=True)
            with ci4:
                chunk_count = len(chunks_list)
                st.markdown(f"""<div class="intel-card">
                  <div class="label">Chunks Retrieved</div>
                  <div class="value" style="color:var(--text-primary);font-size:17px;font-weight:600">{chunk_count}</div>
                </div>""", unsafe_allow_html=True)
            with ci5:
                st.markdown(f"""<div class="intel-card">
                  <div class="label">Response Time</div>
                  <div class="value" style="color:var(--text-primary);font-size:17px;font-weight:600">{execution_time:.2f}s</div>
                </div>""", unsafe_allow_html=True)

            # ── Structured Query Code ──
            if routing_path == "structured" and pandas_code:
                with st.expander("Structured query executed", expanded=False):
                    st.code(pandas_code, language="python")

            # ── Warnings ──
            if low_conf_warn and not abstained:
                st.markdown("""
                <div class="warn-block">
                  Fewer than 3 chunks passed the confidence threshold. The answer may be incomplete.
                </div>
                """, unsafe_allow_html=True)

            # ── Answer ──
            if abstained:
                st.markdown(f"""
                <div class="abstain-block">
                  <div class="label">Insufficient Evidence</div>
                  <div class="msg">{answer}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                answer_placeholder = st.empty()
                if answer_generator:
                    streamed_text = ""
                    for chunk in answer_generator:
                        streamed_text += chunk
                        answer_placeholder.markdown(f"""
                        <div class="answer-block">
                          <div class="section-label">Answer</div>
                          <div class="answer-text">{streamed_text}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    answer = streamed_text # For downstream logic if needed
                else:
                    answer_placeholder.markdown(f"""
                    <div class="answer-block">
                      <div class="section-label">Answer</div>
                      <div class="answer-text">{answer}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # ── Evidence Chunks ──
            if chunks_list:
                st.markdown('<div class="section-label">Evidence</div>', unsafe_allow_html=True)
                for idx, chunk in enumerate(chunks_list, 1):
                    doc_id   = chunk.get("document_id", "")
                    page     = chunk.get("page_number", 0)
                    score    = chunk.get("confidence_score") or chunk.get("score", 0.0)
                    ctype    = chunk.get("chunk_type", "prose")
                    rank     = chunk.get("chunk_rank", idx)
                    cit      = next((c for c in citations if c["document_id"] == doc_id), None)
                    filename = cit["filename"] if (cit and cit.get("filename")) else f"Document {doc_id[:8]}"
                    cited    = any(c["document_id"] == doc_id for c in citations)
                    cite_label = "Cited" if cited else "Retrieved"
                    cite_color = "green" if cited else "gray"

                    page_display = "Summary" if page == -1 else f"Page {page}"
                    with st.expander(
                        f"#{rank}  ·  {filename}  ·  {page_display}  ·  Score {score:.3f}  ·  {cite_label}"
                    ):
                        st.markdown(f"""
                        <div style="margin-bottom:8px">
                          {badge(ctype.upper(), 'gray')}
                          {badge(cite_label, cite_color)}
                        </div>
                        <div style="font-size:13px;color:var(--text-secondary);line-height:1.6;margin-top:12px">
                          {chunk.get('chunk_text', '')}
                        </div>
                        """, unsafe_allow_html=True)

            # ── Source Citations ──
            if citations:
                st.markdown('<div class="section-label">Sources</div>', unsafe_allow_html=True)
                for cit in citations:
                    stype = (cit.get("source_type", "?") or "?").replace("_", " ").title()
                    cit_page = cit.get('page_number', 0)
                    cit_page_display = "Summary" if cit_page == -1 else f"Page {cit_page}"
                    st.markdown(f"""
                    <div style="font-size:13px;color:var(--text-secondary);
                         padding:8px 0;border-bottom:1px solid var(--border)">
                      <strong style="color:var(--text-primary)">{cit.get('filename', 'Unknown')}</strong>
                      &nbsp;·&nbsp; {stype}
                      &nbsp;·&nbsp; {cit_page_display}
                    </div>
                    """, unsafe_allow_html=True)

            end_time = time.time()
            execution_time = end_time - start_time
            status_box.update(label=f"Query complete in {execution_time:.2f}s!", state="complete", expanded=False)

        except Exception as e:
            st.error(f"Error executing RAG pipeline: {e}")

elif ask_btn and not query.strip():
    st.markdown("""
    <div class="warn-block">Please enter a question to continue.</div>
    """, unsafe_allow_html=True)

if not query and not query_disabled:
    st.markdown("""
    <div style="text-align:center;padding:64px 0 32px 0;color:var(--text-muted);font-size:15px">
      Type your question above to begin.
    </div>
    """, unsafe_allow_html=True)
