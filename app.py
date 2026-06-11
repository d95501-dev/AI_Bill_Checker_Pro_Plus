import sqlite3
from datetime import datetime
from io import BytesIO
import streamlit as st
import pandas as pd
from PIL import Image

from config import APP_TITLE, PROVIDERS, DB_PATH
from config import secret_or_default
from db import get_history_df
from ocr_utils import (
    setup_gemini, setup_openai, setup_perplexity, setup_google_vision,
    convert_pdf_to_images, analyze_with_auto_fallback,
    normalize_items, safe_float
)
from excel_export import build_excel_export

def apply_theme_css():
    if st.session_state.get("theme_mode", "light") == "dark":
        st.markdown("""
            <style>
            .stApp { background: #0b1220; color: #e5e7eb; }
            section[data-testid="stSidebar"] { background: #0f172a; }
            section[data-testid="stSidebar"] * { color: #f8fafc !important; }
            </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <style>
            .stApp { background: #f8fafc; color: #0f172a; }
            section[data-testid="stSidebar"] { background: #0f172a; }
            section[data-testid="stSidebar"] * { color: #f8fafc !important; }
            </style>
        """, unsafe_allow_html=True)

def apply_css():
    st.markdown("""
        <style>
        .stApp {
            background: radial-gradient(circle at top left, #ffffff 0%, #eef2ff 45%, #e2e8f0 100%);
        }
        .deep-csc-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 45%, #312e81 100%);
            padding: 28px 30px;
            border-radius: 28px;
            margin-bottom: 18px;
            border: 1px solid rgba(255,255,255,0.10);
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.22), inset 0 1px 0 rgba(255,255,255,0.12);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            flex-wrap: wrap;
        }
        .branding-text h1 {
            margin: 0;
            font-size: 34px !important;
            font-weight: 800;
            background: linear-gradient(to right, #38bdf8, #c084fc, #f43f5e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .branding-text p { margin: 6px 0 0 0; color: #cbd5e1; font-size: 14px; }
        .branding-badge {
            background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%);
            color: white !important;
            padding: 9px 16px;
            border-radius: 999px;
            font-size: 12px !important;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
        }
        .csc-meta-badge {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            color: #e2e8f0 !important;
            padding: 12px 16px;
            border-radius: 16px;
            font-size: 13px !important;
            line-height: 1.7;
        }
        .metric-card {
            background: rgba(255,255,255,0.82);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 22px;
            padding: 18px 20px;
            box-shadow: 0 14px 35px rgba(15, 23, 42, 0.10);
        }
        .metric-label { color: #64748b; font-size: 13px; margin-bottom: 8px; }
        .metric-value { font-size: 28px; font-weight: 800; color: #0f172a; line-height: 1.1; }
        .metric-sub { margin-top: 6px; color: #64748b; font-size: 13px; }
        .section-card {
            background: rgba(255,255,255,0.78);
            border: 1px solid rgba(148,163,184,0.16);
            border-radius: 22px;
            padding: 18px;
        }
        .stButton > button {
            background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            border: none !important;
            border-radius: 14px !important;
            padding: 12px 22px !important;
        }
        </style>
    """, unsafe_allow_html=True)

def metric_card(label, value, sub=""):
    st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-sub">{sub}</div>
        </div>
    """, unsafe_allow_html=True)

def render_metrics(df):
    total_files = len(df) if df is not None and not df.empty else 0
    matched = int((df["status"] == "Matched").sum()) if total_files else 0
    mismatch = int((df["status"] == "Mismatch").sum()) if total_files else 0
    review = int((df["status"] == "Needs Review").sum()) if total_files else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Files Processed", total_files, "Uploaded this session")
    with c2:
        metric_card("Matched Bills", matched, "Auto verified")
    with c3:
        metric_card("Mismatch / Review", mismatch + review, "Needs attention")
    with c4:
        metric_card("OCR Provider", st.session_state.get("selected_provider", "Gemini"), "Current mode")

def make_share_text(df=None):
    total = len(df) if df is not None and not df.empty else 0
    matched = int((df["status"] == "Matched").sum()) if total else 0
    mismatch = int((df["status"] == "Mismatch").sum()) if total else 0
    review = int((df["status"] == "Needs Review").sum()) if total else 0
    return (
        f"{APP_TITLE}\n"
        f"Files Processed: {total}\n"
        f"Matched: {matched}\n"
        f"Mismatch: {mismatch}\n"
        f"Needs Review: {review}"
    )

def share_whatsapp(text):
    import urllib.parse
    return "https://wa.me/?text=" + urllib.parse.quote(text)

def share_telegram(text):
    import urllib.parse
    return "https://t.me/share/url?url=&text=" + urllib.parse.quote(text)

def share_email(text, subject="Bill Dashboard Report"):
    import urllib.parse
    return "mailto:?subject=" + urllib.parse.quote(subject) + "&body=" + urllib.parse.quote(text)

def render_theme_toggle(location="main"):
    mode = st.radio(
        "Theme",
        ["light", "dark"],
        horizontal=True,
        index=0 if st.session_state.get("theme_mode", "light") == "light" else 1,
        key=f"theme_radio_{location}",
    )
    if mode != st.session_state.get("theme_mode", "light"):
        st.session_state["theme_mode"] = mode
        st.rerun()

def login_screen():
    st.markdown("""
        <style>
        .login-wrap {
            max-width: 460px;
            margin: 7vh auto;
            padding: 28px;
            border-radius: 24px;
            background: rgba(255,255,255,0.85);
            box-shadow: 0 20px 60px rgba(15, 23, 42, 0.14);
            border: 1px solid rgba(148,163,184,0.18);
            backdrop-filter: blur(10px);
        }
        .login-title {
            font-size: 32px;
            font-weight: 800;
            margin: 0;
            background: linear-gradient(to right, #0f172a, #4338ca);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .login-sub {
            margin-top: 8px;
            color: #64748b;
            font-size: 14px;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔐 System Login</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-sub">Secure access for AI bill dashboard</div>', unsafe_allow_html=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login Server", use_container_width=True, key="login_btn"):
        if username == secret_or_default("APP_USERNAME", "admin") and password == secret_or_default("APP_PASSWORD", "password123"):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password Credentials")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

def render_upload_module():
    st.markdown("""
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p>Automated structural data parsing pipeline powered by multiple providers.</p>
            </div>
            <div class="csc-meta-badge">📍 <b>Deep CSC</b><br>👤 Owner: Deepak | ID: 256423250015</div>
            <div class="branding-badge">Deep CSC AI</div>
        </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs(["📷 Scan / Upload", "🕘 History", "⚙️ Settings"])

    with tabs[0]:
        st.session_state.selected_provider = st.selectbox(
            "Select OCR Provider",
            PROVIDERS,
            index=PROVIDERS.index(st.session_state.get("selected_provider", "Gemini")),
        )

        uploaded_files = st.file_uploader(
            "Upload Bill Images or PDFs",
            type=["jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            process_now = st.button("Process All Files", use_container_width=True)
        with c2:
            clear_state = st.button("Clear Uploaded / Processed Files", use_container_width=True)

        if clear_state:
            st.session_state.processed_files = set()
            st.rerun()

        model_bundle = {
            "vision_client": setup_google_vision(),
            "gemini": setup_gemini(),
            "perplexity": setup_perplexity(),
            "openai": setup_openai(),
        }

        if uploaded_files and process_now:
            all_results = []
            for uploaded_file in uploaded_files:
                file_key = f"{uploaded_file.name}_{uploaded_file.size}"
                if file_key in st.session_state.processed_files:
                    continue

                file_bytes = uploaded_file.getvalue()
                if uploaded_file.name.lower().endswith(".pdf"):
                    try:
                        pages = convert_pdf_to_images(file_bytes)
                        for i, img in enumerate(pages):
                            data = analyze_with_auto_fallback(model_bundle, img, forced=st.session_state.selected_provider)
                            all_results.append({"page": i + 1, "source": uploaded_file.name, "data": data})
                    except Exception as e:
                        st.error(f"Error processing {uploaded_file.name}: {e}")
                else:
                    img = Image.open(BytesIO(file_bytes)).convert("RGB")
                    data = analyze_with_auto_fallback(model_bundle, img, forced=st.session_state.selected_provider)
                    all_results.append({"page": 1, "source": uploaded_file.name, "data": data})

                st.session_state.processed_files.add(file_key)

            if all_results:
                from db import insert_bill
                df = build_batch_summary(all_results)
                render_metrics(df)

                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.dataframe(df, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

                summary_text = make_share_text(df)
                s1, s2, s3 = st.columns(3)
                with s1:
                    st.link_button("📱 Share on WhatsApp", share_whatsapp(summary_text), use_container_width=True)
                with s2:
                    st.link_button("✈️ Share on Telegram", share_telegram(summary_text), use_container_width=True)
                with s3:
                    st.link_button("📧 Share by Email", share_email(summary_text), use_container_width=True)

                excel_data = build_excel_export(all_results)
                st.download_button(
                    "📥 Download Excel Report",
                    data=excel_data,
                    file_name="Shri_Bala_Ji_Dairy_Bill_Summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    with tabs[1]:
        st.subheader("Processing History")
        history_df = get_history_df()
        st.dataframe(history_df, use_container_width=True)

    with tabs[2]:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        render_theme_toggle("settings")
        st.markdown('</div>', unsafe_allow_html=True)

def build_batch_summary(results):
    rows = []
    for item in results:
        d = item.get("data") or {}
        raw_text = str(d.get("raw_text") or "").strip()
        items = normalize_items(d.get("items"))
        tmp_df = pd.DataFrame(items)
        calc_total = float(pd.to_numeric(tmp_df["amount"], errors="coerce").fillna(0).sum()) if not tmp_df.empty else 0.0
        total = safe_float(d.get("total", 0))
        shop = str(d.get("shop_name") or "").strip()
        bill_date = str(d.get("bill_date") or "").strip()

        if not shop and raw_text:
            for ln in [x.strip() for x in raw_text.splitlines() if x.strip()][:10]:
                if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax)\b", ln, re.I):
                    shop = ln[:80]
                    break

        if not shop:
            shop = "Unknown Shop"
        if not bill_date:
            bill_date = datetime.now().strftime("%Y-%m-%d")

        status = "Needs Review" if total <= 0 else ("Matched" if abs(calc_total - total) < 1 else "Mismatch")
        rows.append({
            "page": item.get("page"),
            "source": item.get("source"),
            "shop_name": shop,
            "bill_date": bill_date,
            "gst_number": d.get("gst_number") or "N/A",
            "bill_total": total,
            "calculated_total": calc_total,
            "difference": abs(calc_total - total),
            "status": status,
        })
    return pd.DataFrame(rows)

def render_app():
    apply_theme_css()
    apply_css()

    if not st.session_state.logged_in:
        login_screen()
    else:
        with st.sidebar:
            st.markdown("### Controls")
            if st.button("Logout", use_container_width=True):
                st.session_state.logged_in = False
                for k in list(st.session_state.keys()):
                    if k != "logged_in":
                        del st.session_state[k]
                st.rerun()
            render_theme_toggle("sidebar")
        render_upload_module()
