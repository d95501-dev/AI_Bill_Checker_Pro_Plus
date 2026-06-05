import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import tempfile
import json
import re
import sqlite3
from datetime import datetime
import base64

try:
    from pdf2image import convert_from_bytes
except Exception:
    convert_from_bytes = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import requests
except Exception:
    requests = None

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
DEFAULT_USERNAME = st.secrets.get("APP_USERNAME", "admin")
DEFAULT_PASSWORD = st.secrets.get("APP_PASSWORD", "password123")

def setup_page():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="expanded",
    )

def apply_css():
    st.markdown("""
        <style>
            .main { background-color: #f8fafc; }
            h1, h2, h3, h4 { font-family: system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
            .deep-csc-header {
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
                padding: 30px; border-radius: 24px; margin-bottom: 35px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px;
            }
            .branding-text h1 {
                background: linear-gradient(to right, #38bdf8, #c084fc, #f43f5e);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                margin: 0; font-size: 34px !important; letter-spacing: -0.5px;
            }
            .csc-meta-badge {
                background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.15);
                padding: 10px 18px; border-radius: 14px; color: #e2e8f0 !important; font-size: 13px !important; line-height: 1.6;
            }
            .branding-badge {
                background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); color: white !important;
                padding: 8px 18px; border-radius: 50px; font-size: 13px !important; font-weight: 700;
                text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 4px 14px rgba(236, 72, 153, 0.4);
            }
            .stSidebar { background-color: #0f172a !important; }
            .sidebar-brand-box {
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%) !important;
                padding: 22px !important;
                border-radius: 16px !important;
                text-align: center !important;
                margin-bottom: 20px !important;
                border: 2px solid #334155 !important;
                box-shadow: 0 6px 12px rgba(0,0,0,0.4) !important;
            }
            .sidebar-title { color: #38bdf8 !important; font-size: 28px !important; font-weight: 900 !important; margin: 0 0 6px 0 !important; }
            .sidebar-subtitle { color: #ff477e !important; font-size: 14px !important; font-weight: 800 !important; text-transform: uppercase !important; letter-spacing: 1px !important; margin-bottom: 12px !important; }
            .sidebar-id-badge { color: #ffffff !important; font-size: 13px !important; font-weight: 700 !important; font-family: monospace !important; background: #1e293b !important; padding: 6px 12px !important; border-radius: 8px !important; display: inline-block !important; border: 1px solid #475569 !important; }
            .stButton>button {
                background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
                color: white !important;
                font-weight: 700 !important;
                padding: 12px 24px !important;
                border-radius: 12px !important;
                border: none !important;
            }
        </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            bill_date TEXT NOT NULL,
            gst_number TEXT,
            total REAL NOT NULL,
            calculated_total REAL NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(shop_name, bill_date, total)
        )
    """)
    conn.commit()
    conn.close()

def insert_bill(shop, date, gst, total, calc_total, status):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO bills
            (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def init_auth():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def init_runtime_state():
    defaults = {
        "selected_provider": "Gemini",
        "gemini_available": True,
        "last_gemini_error_time": None,
        "gemini_cooldown_seconds": 900,
        "gemini_retry_count": 0,
        "batch_results": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def do_login():
    st.title("🔐 System Login Proxy")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login Server", use_container_width=True, key="login_btn"):
        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password Credentials")
    st.stop()

def terminate_session():
    st.session_state.logged_in = False
    for k in list(st.session_state.keys()):
        if k != "logged_in":
            del st.session_state[k]
    st.rerun()

def setup_gemini():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

def setup_openai():
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)

def setup_perplexity():
    return st.secrets.get("PERPLEXITY_API_KEY", "")

def validate_gst(gst_str):
    if not gst_str:
        return False, "N/A"
    gst_regex = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    clean_gst = re.sub(r'[^A-Z0-9]', '', str(gst_str).upper())
    return bool(re.match(gst_regex, clean_gst)), clean_gst

def normalize_items(items):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for it in items:
        if isinstance(it, dict):
            cleaned.append({
                "name": it.get("name") or "",
                "qty": it.get("qty") or "",
                "rate": it.get("rate") or "",
                "amount": it.get("amount") or ""
            })
    return cleaned

def parse_json_from_response(response_text):
    if not response_text:
        raise ValueError("Empty response from model")
    raw = response_text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return json.loads(raw)

def safe_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0

def can_try_gemini():
    if st.session_state.get("gemini_available", True):
        return True
    last_error = st.session_state.get("last_gemini_error_time")
    if not last_error:
        return True
    cooldown = st.session_state.get("gemini_cooldown_seconds", 900)
    return (datetime.now() - last_error).total_seconds() >= cooldown

def build_schema_prompt():
    return """
You are a document extraction specialist.
Extract invoice details and return ONLY valid JSON:
{
  "shop_name": null or string,
  "bill_date": null or string,
  "gst_number": null or string,
  "items": [
    {"name": string, "qty": string, "rate": string, "amount": string}
  ],
  "total": null or string
}
Rules:
- Use only visible text from the document.
- If a field is missing, return null.
- Do not normalize values.
- Do not add explanations.
- Do not wrap in markdown.
"""

def analyze_gemini(model, image):
    response = model.generate_content([build_schema_prompt(), image])
    return parse_json_from_response(getattr(response, "text", ""))

def analyze_openai(client, image):
    if client is None:
        raise RuntimeError("OpenAI not configured")
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=95)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    resp = client.chat.completions.create(
        model=st.secrets.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": build_schema_prompt()},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract invoice JSON from this image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}
        ],
        response_format={"type": "json_object"}
    )
    return parse_json_from_response(resp.choices[0].message.content)

def analyze_perplexity(api_key, image):
    if not api_key or requests is None:
        raise RuntimeError("Perplexity not configured")
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=95)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": st.secrets.get("PERPLEXITY_MODEL", "sonar-pro"),
        "messages": [
            {"role": "system", "content": build_schema_prompt()},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract invoice JSON from this image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "invoice_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "shop_name": {"type": ["string", "null"]},
                        "bill_date": {"type": ["string", "null"]},
                        "gst_number": {"type": ["string", "null"]},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "qty": {"type": "string"},
                                    "rate": {"type": "string"},
                                    "amount": {"type": "string"}
                                },
                                "required": ["name", "qty", "rate", "amount"]
                            }
                        },
                        "total": {"type": ["string", "null"]}
                    },
                    "required": ["shop_name", "bill_date", "gst_number", "items", "total"]
                }
            }
        },
        "temperature": 0.0
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    return parse_json_from_response(r.json()["choices"][0]["message"]["content"])

def analyze_with_auto_fallback(model_bundle, image):
    provider = st.session_state.get("selected_provider", "Gemini")
    order = [provider, "Gemini", "OpenAI", "Perplexity"]
    seen = set()
    last_err = None

    for p in order:
        if p in seen:
            continue
        seen.add(p)
        try:
            if p == "Gemini":
                if model_bundle.get("gemini") and can_try_gemini():
                    result = analyze_gemini(model_bundle["gemini"], image)
                    st.session_state.gemini_available = True
                    st.session_state.last_gemini_error_time = None
                    st.session_state.gemini_retry_count = 0
                    return result
            elif p == "OpenAI" and model_bundle.get("openai"):
                return analyze_openai(model_bundle["openai"], image)
            elif p == "Perplexity" and model_bundle.get("perplexity"):
                return analyze_perplexity(model_bundle["perplexity"], image)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if p == "Gemini" and ("429" in msg or "quota" in msg or "rate limit" in msg):
                st.session_state.gemini_available = False
                st.session_state.last_gemini_error_time = datetime.now()
                st.session_state.gemini_retry_count += 1
                st.warning("Gemini quota exhausted. Switching to next provider.")
            continue

    raise RuntimeError(f"All providers failed: {last_err}")

def render_bill_result(data, source_name, save_to_db=False):
    if not isinstance(data, dict):
        st.error("AI se data nahi mil paaya.")
        return

    shop_name = str(data.get("shop_name") or "Unknown Shop").strip()
    bill_date = str(data.get("bill_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    gst_number = data.get("gst_number") or "N/A"

    st.markdown(f"### 🏪 Vendor: `{shop_name}`")
    c1, c2 = st.columns(2)
    c1.markdown(f"**🗓️ Declared Invoice Date:** {bill_date}")
    is_valid_gst, formatted_gst = validate_gst(gst_number)
    if gst_number != "N/A" and is_valid_gst:
        c2.markdown(f"**🛡️ GSTIN Registry Validation:** :green[✅ Valid - {formatted_gst}]")
    elif gst_number != "N/A":
        c2.markdown(f"**🛡️ GSTIN Registry Validation:** :orange[⚠️ Format Mismatch - {formatted_gst}]")
    else:
        c2.markdown("**🛡️ GSTIN Registry Validation:** :red[ℹ️ Not Disclosed]")

    items = normalize_items(data.get("items"))
    if items:
        df = pd.DataFrame(items)
        st.dataframe(df, use_container_width=True, hide_index=True)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        calculated_total = float(df["amount"].sum())
    else:
        df = pd.DataFrame(columns=["name", "qty", "rate", "amount"])
        calculated_total = 0.0
        st.info("No items detected.")

    bill_total = safe_float(data.get("total", 0))
    diff = abs(calculated_total - bill_total)
    status_txt = "Matched" if diff < 1 else "Mismatch"

    x1, x2 = st.columns(2)
    with x1:
        st.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
    with x2:
        st.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")

    if status_txt == "Matched":
        st.success("🎯 Auto-Arithmetic Audit Pass.")
    else:
        st.error(f"🛑 Audit Discrepancy Found: ₹{diff:,.2f}")

    if save_to_db:
        saved = insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt)
        if saved:
            st.toast("Saved to DB", icon="💾")

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Parsed Invoice Data")

    safe_shop = re.sub(r'[^A-Za-z0-9_-]+', '_', shop_name)
    safe_source = re.sub(r'[^A-Za-z0-9_-]+', '_', str(source_name))
    st.download_button(
        "📥 Export Excel Data Sheets",
        data=excel_buffer.getvalue(),
        file_name=f"{safe_shop}_ledger.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"excel_{safe_source}"
    )

    pdf_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(pdf_temp.name)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"Invoice Summary: {shop_name}", styles["Title"]),
        Spacer(1, 10),
        Paragraph(f"Date: {bill_date} | GSTIN: {gst_number}", styles["Normal"]),
        Paragraph(f"Verified Final Amount: INR {bill_total:.2f}", styles["Heading3"])
    ]
    doc.build(elements)
    with open(pdf_temp.name, "rb") as f:
        st.download_button(
            "📄 Download Sign-off PDF",
            f.read(),
            file_name=f"{safe_shop}_receipt.pdf",
            mime="application/pdf",
            use_container_width=True,
            key=f"pdf_{safe_source}"
        )

def build_batch_summary(results):
    rows = []
    for item in results:
        if item.get("data"):
            data = item["data"]
            shop_name = str(data.get("shop_name") or "Unknown Shop").strip()
            bill_date = str(data.get("bill_date") or datetime.now().strftime("%Y-%m-%d")).strip()
            gst_number = data.get("gst_number") or "N/A"
            items = normalize_items(data.get("items"))

            if items:
                tmp_df = pd.DataFrame(items)
                tmp_df["amount"] = pd.to_numeric(tmp_df["amount"], errors="coerce").fillna(0)
                calculated_total = float(tmp_df["amount"].sum())
            else:
                calculated_total = 0.0

            bill_total = safe_float(data.get("total", 0))
            diff = abs(calculated_total - bill_total)
            status_txt = "Matched" if diff < 1 else "Mismatch"

            rows.append({
                "page": item.get("page"),
                "source": item.get("source"),
                "shop_name": shop_name,
                "bill_date": bill_date,
                "gst_number": gst_number,
                "bill_total": bill_total,
                "calculated_total": calculated_total,
                "difference": diff,
                "status": status_txt
            })
        else:
            rows.append({
                "page": item.get("page"),
                "source": item.get("source"),
                "shop_name": None,
                "bill_date": None,
                "gst_number": None,
                "bill_total": None,
                "calculated_total": None,
                "difference": None,
                "status": f"Error: {item.get('error')}"
            })
    return pd.DataFrame(rows)

def make_excel_download(df, filename, label="📥 Download Excel", key="excel_download"):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Batch Summary")
    st.download_button(
        label,
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=key
    )

def process_pdf_pages(model_bundle, pdf_bytes, source_name):
    if convert_from_bytes is None:
        raise RuntimeError("pdf2image not installed. Run: pip install pdf2image")
    results = []
    pages = convert_from_bytes(pdf_bytes, dpi=300)
    for p_idx, page_img in enumerate(pages, start=1):
        try:
            data = analyze_with_auto_fallback(model_bundle, page_img)
            results.append({"page": p_idx, "source": source_name, "data": data, "error": None})
        except Exception as e:
            results.append({"page": p_idx, "source": source_name, "data": None, "error": str(e)})
    return results

def render_upload_module(model_bundle):
    st.markdown(
        '<div class="deep-csc-header"><div class="branding-text"><h1>🧾 AI Multi-Bill OCR Processor</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by multiple providers.</p></div><div class="csc-meta-badge">📍 <b>Deep Digital Seva Kendra</b><br>👤 Owner: Deepak | ID: 256423250015</div><div class="branding-badge">Deep CSC AI</div></div>',
        unsafe_allow_html=True
    )

    providers = ["Gemini", "OpenAI", "Perplexity"]
    provider = st.selectbox("Choose provider", providers, index=providers.index(st.session_state.selected_provider), key="provider_select")
    st.session_state.selected_provider = provider

    if st.button("🔄 Retry Gemini Now", key="retry_gemini", use_container_width=True):
        st.session_state.gemini_available = True
        st.session_state.last_gemini_error_time = None
        st.session_state.gemini_retry_count = 0
        st.success("Gemini retry enabled. Next request will try Gemini first.")

    uploaded_files = st.file_uploader(
        "Drop batch bill images or PDF files below (Multi-upload supported)",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True
    )
    if not uploaded_files:
        return

    for idx, file in enumerate(uploaded_files):
        st.markdown("---")
        st.subheader(f"📄 Processing Block [{idx + 1}]: {file.name}")
        is_pdf = file.name.lower().endswith(".pdf")

        if is_pdf:
            pdf_bytes = file.getvalue()
            if convert_from_bytes is None:
                st.error("PDF parsing error: pdf2image not installed")
                continue

            try:
                pages = convert_from_bytes(pdf_bytes, dpi=300)
            except Exception as e:
                st.error(f"PDF parsing error: {e}")
                continue

            st.info(f"📁 PDF Document Detected — {len(pages)} page(s) found")

            if st.button("⚡ Process All Pages", key=f"process_all_{idx}", use_container_width=True):
                with st.spinner("Processing all PDF pages..."):
                    st.session_state.batch_results[file.name] = process_pdf_pages(model_bundle, pdf_bytes, file.name)
                st.success("All pages processed successfully!")

            results = st.session_state.batch_results.get(file.name, [])

            for p_idx, page_img in enumerate(pages, start=1):
                st.markdown(f"### 📄 Page {p_idx}")
                st.image(page_img, caption=f"{file.name} - Page {p_idx}", use_container_width=True)

            if results:
                st.markdown("## 📋 Page-wise Consolidated Summary")
                summary_df = build_batch_summary(results)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                make_excel_download(
                    summary_df,
                    f"{file.name}_page_wise_summary.xlsx",
                    label="📥 Download Batch Excel",
                    key=f"batch_excel_{idx}"
                )

                st.markdown("## ✅ Batch Results")
                for item in results:
                    if item["error"]:
                        st.error(f"Page {item['page']}: {item['error']}")
                    else:
                        st.markdown(f"### Page {item['page']} Result")
                        render_bill_result(item["data"], f"{item['source']} (Page {item['page']})", save_to_db=False)

        else:
            col_img, col_act = st.columns([1, 2], gap="large")
            with col_img:
                image = Image.open(BytesIO(file.getvalue())).convert("RGB")
                st.image(image, caption=f"Source: {file.name}", use_container_width=True)
            with col_act:
                if st.button("⚡ Execute AI Analysis", key=f"btn_{idx}", use_container_width=True):
                    with st.spinner("AI engine parsing structural metadata..."):
                        try:
                            data = analyze_with_auto_fallback(model_bundle, image)
                            render_bill_result(data, file.name, save_to_db=True)
                        except Exception as e:
                            st.error(f"Structural Parsing Fault: {e}")

def main():
    setup_page()
    apply_css()
    init_db()
    init_auth()
    init_runtime_state()

    model_bundle = {
        "gemini": setup_gemini(),
        "openai": setup_openai(),
        "perplexity": setup_perplexity(),
    }

    if not st.session_state.logged_in:
        do_login()

    with st.sidebar:
        st.markdown("""
            <div class="sidebar-brand-box">
                <div class="sidebar-title">Deep CSC</div>
                <div class="sidebar-subtitle">Deep Digital Seva Kendra</div>
                <div class="sidebar-id-badge">ID: 256423250015</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown(
            f"<p style='color:#cbd5e1; font-size:14px; margin-left:5px;'>Operator: <b style='color:#38bdf8;'>{DEFAULT_USERNAME} (Deepak)</b></p>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<p style='color:#cbd5e1; font-size:13px; margin-left:5px;'>Gemini state: <b>{'Available' if st.session_state.gemini_available else 'Fallback mode'}</b></p>",
            unsafe_allow_html=True
        )
        st.selectbox("Navigate System", ["📤 Upload & Process"], key="app_mode")
        st.markdown("<br><br><hr style='border-color: #1e293b;'>", unsafe_allow_html=True)
        if st.button("🚪 Terminate Session", use_container_width=True, key="terminate_session"):
            terminate_session()

    render_upload_module(model_bundle)

if __name__ == "__main__":
    main()
