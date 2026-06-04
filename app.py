import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import urllib.parse
import tempfile
import json
import re
import sqlite3
from datetime import datetime
import time
import os
import subprocess
from pdf2image import convert_from_bytes

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
DEFAULT_USERNAME = st.secrets.get("APP_USERNAME", "admin")
DEFAULT_PASSWORD = st.secrets.get("APP_PASSWORD", "password123")
NAPS2_PATH = r"C:\Program Files\NAPS2\NAPS2.exe"

def setup_page():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="expanded"
    )

def apply_css():
    st.markdown("""
        <style>
            .main { background-color: #f8fafc; }
            h1, h2, h3, h4 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
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
            div[data-testid="stMetric"] {
                background: #ffffff !important; padding: 24px !important; border-radius: 20px !important;
                box-shadow: 0 12px 20px -3px rgba(15, 23, 42, 0.04) !important;
            }
            div[data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 800 !important; }
            div[data-testid="stMetricLabel"] { font-size: 12px !important; text-transform: uppercase !important; font-weight: 700 !important; color: #64748b !important; }
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
            .sidebar-title {
                color: #38bdf8 !important;
                font-size: 28px !important;
                font-weight: 900 !important;
                margin: 0 0 6px 0 !important;
                letter-spacing: 0.5px !important;
            }
            .sidebar-subtitle {
                color: #ff477e !important;
                font-size: 14px !important;
                font-weight: 800 !important;
                text-transform: uppercase !important;
                letter-spacing: 1px !important;
                margin-bottom: 12px !important;
            }
            .sidebar-id-badge {
                color: #ffffff !important;
                font-size: 13px !important;
                font-weight: 700 !important;
                font-family: monospace !important;
                background: #1e293b !important;
                padding: 6px 12px !important;
                border-radius: 8px !important;
                display: inline-block !important;
                border: 1px solid #475569 !important;
            }
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
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO bills
            (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            shop, date, gst, total, calc_total, status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Duplicate entry detected!"
        return True, "Successfully logged into DB"
    except sqlite3.OperationalError as e:
        return False, f"Database error: {str(e)}"
    finally:
        if conn:
            conn.close()

def init_auth():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def do_login():
    st.markdown(
        "<div style='text-align:center; padding:20px;'><h2 style='color:#4f46e5; font-size:42px; font-weight:900;'>Deep CSC</h2><p style='color:#64748b;'>Authorized Digital Seva AI Portal</p></div>",
        unsafe_allow_html=True
    )
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
        st.error("Please configure GEMINI_API_KEY in your Streamlit secrets.")
        st.stop()
    genai.configure(api_key=api_key)
    try:
        return genai.GenerativeModel("gemini-2.5-flash")
    except Exception as e:
        st.error(f"Model Initialization Failed: {e}")
        st.stop()

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

def analyze_bill(model, file_payload):
    prompt = """
Return only valid JSON with:
{
  "shop_name": string or null,
  "bill_date": string or null,
  "gst_number": string or null,
  "items": [{"name": string, "qty": number/string, "rate": number/string, "amount": number/string}],
  "total": number/string or null
}
No markdown, no explanation, no extra text.
"""
    last_error = None
    for attempt in range(3):
        try:
            response = model.generate_content([prompt, file_payload])
            text = getattr(response, "text", None)
            return parse_json_from_response(text)
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if ("429" in msg or "quota" in msg) and attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            raise
    raise last_error

def safe_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0

def process_pdf_pages(model, pdf_bytes, source_name):
    results = []
    pages = convert_from_bytes(pdf_bytes, dpi=200)
    for p_idx, page_img in enumerate(pages, start=1):
        try:
            data = analyze_bill(model, page_img)
            results.append({
                "page": p_idx,
                "source": source_name,
                "data": data,
                "error": None
            })
        except Exception as e:
            results.append({
                "page": p_idx,
                "source": source_name,
                "data": None,
                "error": str(e)
            })
    return results

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

def render_bill_result(data, source_name, save_to_db=False):
    if not isinstance(data, dict):
        st.error("AI से डेटा प्राप्त नहीं हो सका।")
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
        st.markdown("<h4 style='font-size:18px; margin-top:20px;'>Detailed Line-Item Breakdown</h4>", unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        calculated_total = float(df["amount"].sum())
    else:
        calculated_total = 0.0
        df = pd.DataFrame(columns=["name", "qty", "rate", "amount"])
        st.info("No items detected.")

    bill_total = safe_float(data.get("total", 0))
    diff = abs(calculated_total - bill_total)
    status_txt = "Matched" if diff < 1 else "Mismatch"

    st.markdown("<h4 style='font-size:18px; margin-top:20px;'>Arithmetic Audit Engine</h4>", unsafe_allow_html=True)
    x1, x2 = st.columns(2)
    with x1:
        st.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
    with x2:
        st.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")

    if status_txt == "Matched":
        st.success("🎯 Auto-Arithmetic Audit Pass: Balance sheet matches perfectly.")
    else:
        st.error(f"🛑 Audit Discrepancy Found: Leakage variance of ₹{diff:,.2f}")

    if save_to_db:
        saved, db_msg = insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt)
        if saved:
            st.toast(f"Saved: {db_msg}", icon="💾")
        else:
            st.toast(f"Skipped: {db_msg}", icon="🚨")

    st.markdown("---")
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Parsed Invoice Data")

    safe_shop = re.sub(r'[^A-Za-z0-9_-]+', '_', shop_name)
    unique_id = re.sub(r'[^A-Za-z0-9_-]+', '_', str(source_name))

    st.download_button(
        "📥 Export Excel Data Sheets",
        data=excel_buffer.getvalue(),
        file_name=f"{safe_shop}_ledger.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"excel_{unique_id}"
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

    ut2, ut3 = st.columns(2)
    with ut2:
        with open(pdf_temp.name, "rb") as f:
            st.download_button(
                "📄 Download Sign-off PDF",
                f.read(),
                file_name=f"{safe_shop}_receipt.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"pdf_{unique_id}"
            )
    with ut3:
        msg_string = f"AI Bill Report - Shop: {shop_name}, Date: {bill_date}, Total: {bill_total:.2f}, Audit: {status_txt}"
        wa_url = "https://wa.me/?text=" + urllib.parse.quote(msg_string)
        st.link_button("📱 Forward Summary to WhatsApp", wa_url, use_container_width=True)

def render_upload_module(model):
    st.markdown(
        '<div class="deep-csc-header"><div class="branding-text"><h1>🧾 AI Multi-Bill OCR Processor</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by Gemini Vision Core.</p></div><div class="csc-meta-badge">📍 <b>Deep Digital Seva Kendra</b><br>👤 Owner: Deepak | ID: 256423250015</div><div class="branding-badge">Deep CSC AI</div></div>',
        unsafe_allow_html=True
    )

    if "scanned_file_path" in st.session_state and st.session_state.scanned_file_path:
        st.info("🔄 Hardware Scanner se data received! Neeche preview dekhein.")
        if st.button("🗑️ Clear Scanned File Cache", key="clear_scan_cache"):
            if os.path.exists(st.session_state.scanned_file_path):
                os.remove(st.session_state.scanned_file_path)
            st.session_state.scanned_file_path = None
            st.rerun()

        st.markdown("---")
        st.subheader("📸 Scanned Document Block")
        col_img, col_act = st.columns([1, 2], gap="large")

        with col_img:
            image = Image.open(st.session_state.scanned_file_path)
            st.image(image, caption="Scanned via NAPS2", use_container_width=True)

        with col_act:
            if st.button("⚡ Execute AI Analysis (Scanned Item)", key="btn_scanned", use_container_width=True):
                with st.spinner("AI engine parsing hardware scanner data..."):
                    try:
                        data = analyze_bill(model, image)
                        render_bill_result(data, "naps2_scan.png", save_to_db=True)
                    except Exception as e:
                        st.error(f"Structural Parsing Fault: {e}")

    uploaded_files = st.file_uploader(
        "Drop batch bill images or PDF files below (Multi-upload supported)",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True
    )

    if not uploaded_files:
        return

    if "batch_results" not in st.session_state:
        st.session_state.batch_results = {}

    for idx, file in enumerate(uploaded_files):
        st.markdown("---")
        st.subheader(f"📄 Processing Block [{idx + 1}]: {file.name}")
        is_pdf = file.name.lower().endswith(".pdf")

        if is_pdf:
            pdf_bytes = file.read()
            try:
                pages = convert_from_bytes(pdf_bytes, dpi=200)
            except Exception as e:
                st.error(f"PDF parsing error: {e}")
                continue

            st.info(f"📁 PDF Document Detected — {len(pages)} page(s) found")

            if st.button("⚡ Process All Pages", key=f"process_all_{idx}", use_container_width=True):
                with st.spinner("Processing all PDF pages..."):
                    st.session_state.batch_results[file.name] = process_pdf_pages(model, pdf_bytes, file.name)
                st.success("All pages processed successfully!")

            results = st.session_state.batch_results.get(file.name, [])

            for p_idx, page_img in enumerate(pages, start=1):
                st.markdown(f"### 📄 Page {p_idx}")
                col_img, _ = st.columns([1, 2], gap="large")
                with col_img:
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

                if st.button("💾 Save All Results to Database", key=f"save_all_{idx}", use_container_width=True):
                    saved_count = 0
                    for item in results:
                        if item["data"]:
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
                            status_txt = "Matched" if abs(calculated_total - bill_total) < 1 else "Mismatch"
                            ok, _ = insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt)
                            if ok:
                                saved_count += 1
                    st.success(f"{saved_count} result(s) saved to database.")

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
                image = Image.open(file)
                st.image(image, caption=f"Source: {file.name}", use_container_width=True)

            with col_act:
                if st.button("⚡ Execute AI Analysis", key=f"btn_{idx}", use_container_width=True):
                    with st.spinner("AI engine parsing structural metadata..."):
                        try:
                            data = analyze_bill(model, image)
                            render_bill_result(data, file.name, save_to_db=True)
                        except Exception as e:
                            st.error(f"Structural Parsing Fault: {e}")

def render_hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        with col_scan:
            st.markdown("#### 📷 Scanner Interface (NAPS2 Integration)")
            scan_dpi = st.select_slider("Select Resolution (DPI)", options=[150, 300, 600], value=300)
            output_format = st.radio("Output File Format", ["PNG", "PDF"], horizontal=True)

            if st.button("🚀 Trigger Flatbed Scan", key="trigger_scan"):
                if not os.path.exists(r"C:\\"):
                    st.error("❌ Yeh feature sirf Local Computer (PC) par chalega, Cloud par nahi!")
                elif not os.path.exists(NAPS2_PATH):
                    st.error(f"❌ NAPS2 software is path par nahi mila: '{NAPS2_PATH}'. Kripya install karein.")
                else:
                    with st.spinner("Connecting to NAPS2 Driver & Scanner Hardware..."):
                        try:
                            ext = ".png" if output_format == "PNG" else ".pdf"
                            temp_scan_file = os.path.join(tempfile.gettempdir(), f"naps2_scan_{int(time.time())}{ext}")
                            cmd = [
                                NAPS2_PATH,
                                "-o", temp_scan_file,
                                "--dpi", str(scan_dpi),
                                "--force"
                            ]
                            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                            if os.path.exists(temp_scan_file) and os.path.getsize(temp_scan_file) > 0:
                                st.success("Scan Completed Successfully!")
                                st.session_state.scanned_file_path = temp_scan_file
                                st.rerun()
                            else:
                                st.error("Scanner file successfully generate nahi kar paaya.")
                        except subprocess.CalledProcessError as e:
                            st.error(f"NAPS2 Hardware Interface Error: {e.stderr}")
                        except Exception as e:
                            st.error(f"Driver connection failure: {str(e)}")

        with col_print:
            st.markdown("#### 🖨️ Printer Interface")
            printer_name = st.selectbox("Select Printer", ["Default System Printer", "HP LaserJet Pro", "Canon Pixma"], key="printer_name")
            copies = st.number_input("Number of Copies", min_value=1, value=1, key="copies")
            if st.button("🖨️ Send to Printer", key="send_printer"):
                st.info(f"Sending {copies} copies to {printer_name}...")

def render_dashboard():
    st.markdown(
        '<div class="deep-csc-header"><div class="branding-text"><h1>📊 Financial Operations Command Center</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Real-time telemetry, duplicate transaction logs, and ledger integrity checks.</p></div><div class="csc-meta-badge">🏢 <b>Deep Digital Seva Kendra</b><br>🔑 Authorized Identity: Deepak [256423250015]</div><div class="branding-badge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">Created by Deep CSC</div></div>',
        unsafe_allow_html=True
    )

    conn = sqlite3.connect(DB_PATH)
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()

    if df_db.empty:
        st.markdown(
            "<div style='background-color: #eff6ff; border-left: 5px solid #4f46e5; padding: 22px; border-radius: 14px; margin-top:20px;'><h4 style='color: #1e40af !important; margin:0 0 8px 0; font-size:18px;'>🏪 Welcome to Deep CSC Dashboard Panel</h4><p style='color: #1e3a8a; margin:0; font-size:14px; line-height:1.6;'>Abhi system database mein koi logs active nahi hain. Bills process karne ke baad dashboard yahan populated hoga.</p></div>",
            unsafe_allow_html=True
        )
        return

    df_db["total"] = pd.to_numeric(df_db["total"], errors="coerce").fillna(0)
    total_spent = float(df_db["total"].sum())
    total_invoices = len(df_db)
    mismatched_count = int((df_db["status"] == "Mismatch").sum())

    db1, db2, db3 = st.columns(3, gap="large")
    with db1:
        st.metric("💰 Aggregate Pipeline Spend", f"₹{total_spent:,.2f}")
    with db2:
        st.metric("📄 Corporate Vouchers Audited", f"{total_invoices} Bills")
    with db3:
        st.metric("⚠️ Failed Integrity Mismatches", f"{mismatched_count} Issues" if mismatched_count else "✅ System Integrity Audit")

    st.markdown("<br><hr style='border-color: #e2e8f0;'><br>", unsafe_allow_html=True)

    graph_col1, graph_col2 = st.columns([2, 1], gap="large")
    with graph_col1:
        st.markdown("<h3 style='font-size:19px; margin-bottom:15px; color:#4f46e5 !important;'>📈 Top Vendors Distribution</h3>", unsafe_allow_html=True)
        chart_data = (
            df_db.groupby("shop_name", dropna=False)["total"]
            .sum()
            .reset_index()
            .sort_values(by="total", ascending=False)
            .head(8)
        )
        st.bar_chart(chart_data.set_index("shop_name")["total"], color="#4f46e5")
    with graph_col2:
        st.markdown("<h3 style='font-size:19px; margin-bottom:15px; color:#10b981 !important;'>📊 Ledger Audit Split</h3>", unsafe_allow_html=True)
        status_distribution = df_db["status"].value_counts().reset_index()
        status_distribution.columns = ["Audit Status", "Volume Counter"]
        st.dataframe(status_distribution, use_container_width=True, hide_index=True)

    st.markdown("<br><hr style='border-color: #e2e8f0;'><br>", unsafe_allow_html=True)
    st.markdown("<h3 style='font-size:22px;'>🔍 Centralized Ledger Records Registry</h3>", unsafe_allow_html=True)

    query_col, export_col = st.columns([3, 1], gap="medium")
    with query_col:
        search_query = st.text_input("⚡ Smart Filter (Input target Vendor Name / Retail Shop keyword string)", key="dashboard_search")
    with export_col:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        master_excel_buffer = BytesIO()
        with pd.ExcelWriter(master_excel_buffer, engine="openpyxl") as writer:
            df_db.to_excel(writer, index=False, sheet_name="Master DB Sheet")
        st.download_button(
            "📥 Master Export DB Logs",
            data=master_excel_buffer.getvalue(),
            file_name="Corporate_Master_Ledger.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="master_export_db"
        )

    filtered_df = df_db
    if search_query:
        filtered_df = df_db[df_db["shop_name"].astype(str).str.contains(search_query, case=False, na=False)]

    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

def main():
    setup_page()
    apply_css()
    init_db()
    init_auth()
    model = setup_gemini()

    if "scanned_file_path" not in st.session_state:
        st.session_state.scanned_file_path = None

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

        st.markdown(f"<p style='color:#cbd5e1; font-size:14px; margin-left:5px;'>Operator: <b style='color:#38bdf8;'>{DEFAULT_USERNAME} (Deepak)</b></p>", unsafe_allow_html=True)
        app_mode = st.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"], key="app_mode")
        st.markdown("<br><br><hr style='border-color: #1e293b;'>", unsafe_allow_html=True)

        if st.button("🚪 Terminate Session", use_container_width=True, key="terminate_session"):
            terminate_session()

    if app_mode == "📤 Upload & Process":
        render_upload_module(model)
        render_hardware_module()
    else:
        render_dashboard()

if __name__ == "__main__":
    main()
