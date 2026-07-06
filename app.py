import os
import re
import json
import hashlib
import sqlite3
import zipfile
import shutil
from datetime import datetime
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st
from PIL import Image

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

# ============================================
# APP CONFIG
# ============================================

APP_TITLE = "Deep CSC AI Bill Processor V2"
DB_PATH = "bills_v2.db"
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================
# SECURITY
# ============================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

# ============================================
# DEFAULT USERS
# ============================================

USERS = {
    "admin": {
        "password": hash_password("admin123"),
        "role": "admin"
    },
    "operator": {
        "password": hash_password("operator123"),
        "role": "operator"
    },
    "viewer": {
        "password": hash_password("viewer123"),
        "role": "viewer"
    }
}

# ============================================
# DATABASE
# ============================================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bills(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            shop_name TEXT,
            bill_date TEXT,
            gst_number TEXT,
            total REAL,
            calculated_total REAL,
            status TEXT,
            created_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            timestamp TEXT
        )
        """)
        conn.commit()

# ============================================
# AUDIT LOG
# ============================================

def log_action(username, action):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (username, action, timestamp)
            VALUES (?, ?, ?)
            """,
            (
                username,
                action,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()

# ============================================
# LOGIN
# ============================================

def login_screen():
    st.title("🔐 Deep CSC Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username in USERS:
            if verify_password(password, USERS[username]["password"]):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = USERS[username]["role"]
                log_action(username, "LOGIN")
                st.rerun()
        st.error("Invalid Login")

# ============================================
# SESSION INIT
# ============================================

def init_session():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "results" not in st.session_state:
        st.session_state.results = []

# ============================================
# DUPLICATE DETECTOR
# ============================================

def generate_bill_hash(shop, bill_date, total):
    raw = f"{shop}_{bill_date}_{total}"
    return hashlib.md5(raw.encode()).hexdigest()

try:
    import google.generativeai as genai
except:
    genai = None

try:
    from openai import OpenAI
except:
    OpenAI = None

try:
    from google.cloud import vision
except:
    vision = None

# ============================================
# IMAGE PREPROCESSING
# ============================================

def preprocess_image(image):
    image = image.convert("L")
    image = image.point(lambda x: 0 if x < 150 else 255, "1")
    return image

# ============================================
# GST VALIDATION
# ============================================

GST_REGEX = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"

def validate_gst(gst):
    if not gst:
        return False
    gst = re.sub(r"[^A-Z0-9]", "", str(gst).upper())
    return bool(re.match(GST_REGEX, gst))

# ============================================
# INVOICE NUMBER EXTRACTION (FALLBACK)
# ============================================

def extract_invoice_number(text):
    patterns = [
        r"invoice\s*no\.?\s*[:\-]?\s*([A-Z0-9\-\/]+)",
        r"bill\s*no\.?\s*[:\-]?\s*([A-Z0-9\-\/]+)",
        r"inv\s*[:\-]?\s*([A-Z0-9\-\/]+)"
    ]
    text = str(text)
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return "N/A"

# ============================================
# TOTAL EXTRACTION (FALLBACK)
# ============================================

def extract_total(text):
    patterns = [
        r"grand\s*total\s*[:\-]?\s*(\d+\.\d+)",
        r"net\s*amount\s*[:\-]?\s*(\d+\.\d+)",
        r"total\s*[:\-]?\s*(\d+\.\d+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except:
                pass
    return 0.0

# ============================================
# GEMINI SETUP
# ============================================

@st.cache_resource
def setup_gemini():
    if genai is None:
        return None
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

# ============================================
# OPENAI SETUP
# ============================================

@st.cache_resource
def setup_openai():
    if OpenAI is None:
        return None
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

# ============================================
# GOOGLE VISION
# ============================================

@st.cache_resource
def setup_google_vision():
    if vision is None:
        return None
    return vision.ImageAnnotatorClient()

# ============================================
# OCR PROMPT
# ============================================

def build_ocr_prompt():
    return """
Extract invoice data accurately.
Return ONLY a valid JSON object. Do not include markdown code blocks or any explanation text.

{
  "shop_name": "",
  "invoice_number": "",
  "bill_date": "",
  "gst_number": "",
  "items": [
      {
        "name": "",
        "qty": "",
        "rate": "",
        "amount": ""
      }
  ],
  "total": 0.0
}
"""

# ============================================
# GEMINI OCR
# ============================================

def run_gemini_ocr(model, image_bytes):
    try:
        response = model.generate_content(
            [
                build_ocr_prompt(),
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]
        )
        return response.text
    except Exception as e:
        return str(e)

# ============================================
# GOOGLE VISION OCR
# ============================================

def run_google_vision_ocr(client, image_bytes):
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)
    if response.full_text_annotation:
        return response.full_text_annotation.text
    return ""

# ============================================
# OCR AUTO ROUTER
# ============================================

def perform_ocr(image, provider, gemini_model=None, openai_client=None, vision_client=None):
    image = preprocess_image(image)
    buf = BytesIO()
    image.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    if provider == "Gemini":
        return run_gemini_ocr(gemini_model, image_bytes)
    elif provider == "Google Vision":
        return run_google_vision_ocr(vision_client, image_bytes)
    return ""

# ============================================
# FRAUD DETECTOR
# ============================================

def detect_fraud(bill_total, calculated_total):
    difference = abs(bill_total - calculated_total)
    return difference > 5

try:
    import fitz
except:
    fitz = None

try:
    import pypdfium2 as pdfium
except:
    pdfium = None

try:
    from pdf2image import convert_from_bytes
except:
    convert_from_bytes = None

# ============================================
# PDF TO IMAGES
# ============================================

def pdf_to_images(pdf_bytes):
    images = []
    if fitz:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        return images
    if pdfium:
        pdf = pdfium.PdfDocument(pdf_bytes)
        for i in range(len(pdf)):
            img = pdf[i].render(scale=4).to_pil()
            images.append(img.convert("RGB"))
        return images
    if convert_from_bytes:
        return convert_from_bytes(pdf_bytes, dpi=300)
    return []

# ============================================
# ZIP EXTRACTOR
# ============================================

def extract_zip(uploaded_zip):
    extracted_files = []
    temp_dir = "temp_zip"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    with zipfile.ZipFile(uploaded_zip) as zip_ref:
        zip_ref.extractall(temp_dir)
    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            full_path = os.path.join(root, file)
            extracted_files.append(full_path)
    return extracted_files

# ============================================
# FILE HASH
# ============================================

def generate_file_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()

def is_duplicate_file(file_hash, processed_hashes):
    return file_hash in processed_hashes

# ============================================
# PROCESS SINGLE IMAGE
# ============================================

def process_single_image(image, provider, model_bundle):
    try:
        text = perform_ocr(
            image=image,
            provider=provider,
            gemini_model=model_bundle.get("gemini"),
            openai_client=model_bundle.get("openai"),
            vision_client=model_bundle.get("vision")
        )
        return text
    except Exception as e:
        return str(e)

# ============================================
# MULTI THREAD OCR
# ============================================

def process_images_parallel(images, provider, model_bundle):
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_single_image, img, provider, model_bundle) for img in images]
        for future in futures:
            try:
                results.append(future.result())
            except Exception:
                pass
    return results

# ============================================
# PDF PROCESSOR
# ============================================

def process_pdf_file(pdf_bytes, provider, model_bundle):
    images = pdf_to_images(pdf_bytes)
    return process_images_parallel(images, provider, model_bundle)

# ============================================
# IMAGE PROCESSOR
# ============================================

def process_image_file(image_bytes, provider, model_bundle):
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    return process_single_image(image, provider, model_bundle)

# ============================================
# PROGRESS BAR
# ============================================

def update_progress(current, total, progress_bar):
    if total == 0:
        return
    percent = current / total
    progress_bar.progress(percent)

# ============================================
# BATCH PROCESSOR (FIXED MECHANISM & DB WORK)
# ============================================

def process_batch(uploaded_files, provider, model_bundle):
    all_results = []
    processed_hashes = set()
    progress_bar = st.progress(0)
    total_files = len(uploaded_files)
    current = 0

    for file in uploaded_files:
        try:
            file_bytes = file.getvalue()
            file_hash = generate_file_hash(file_bytes)

            if is_duplicate_file(file_hash, processed_hashes):
                continue
            processed_hashes.add(file_hash)

            if file.name.lower().endswith(".pdf"):
                ocr_outputs = process_pdf_file(file_bytes, provider, model_bundle)
                ocr_raw = " ".join(ocr_outputs) if isinstance(ocr_outputs, list) else str(ocr_outputs)
            else:
                ocr_raw = process_image_file(file_bytes, provider, model_bundle)

            # JSON Parsing and Structured Normalisation
            parsed_data = {}
            try:
                clean_json = re.sub(r"```json\s*|```", "", ocr_raw).strip()
                parsed_data = json.loads(clean_json)
            except Exception:
                parsed_data = {
                    "invoice_number": extract_invoice_number(ocr_raw),
                    "shop_name": "Unknown Vendor",
                    "bill_date": datetime.now().strftime("%Y-%m-%d"),
                    "gst_number": "",
                    "total": extract_total(ocr_raw),
                    "items": []
                }

            # Business math calculation check
            try:
                calc_total = sum(float(i.get('amount') or 0) for i in parsed_data.get('items', []))
            except:
                calc_total = 0.0

            try:
                b_total = float(parsed_data.get("total") or 0)
            except:
                b_total = 0.0

            if calc_total == 0.0:
                calc_total = b_total

            status = "Mismatch" if detect_fraud(b_total, calc_total) else "Matched"
            parsed_data["status"] = status

            # SAVE SECURELY INTO SQLITE
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO bills (invoice_number, shop_name, bill_date, gst_number, total, calculated_total, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(parsed_data.get("invoice_number", "")),
                    str(parsed_data.get("shop_name", "")),
                    str(parsed_data.get("bill_date", "")),
                    str(parsed_data.get("gst_number", "")),
                    b_total,
                    calc_total,
                    status,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()

            all_results.append(parsed_data)
            current += 1
            update_progress(current, total_files, progress_bar)
        except Exception as e:
            st.error(f"{file.name}: {e}")

    return all_results

try:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
except:
    SimpleDocTemplate = None

try:
    import plotly.express as px
except:
    px = None

# ============================================
# BUILD SUMMARY DATAFRAME
# ============================================

def build_summary_dataframe(results):
    rows = []
    for item in results:
        rows.append({
            "Invoice": item.get("invoice_number", ""),
            "Shop": item.get("shop_name", ""),
            "Date": item.get("bill_date", ""),
            "GST": item.get("gst_number", ""),
            "Total": float(item.get("total") or 0),
            "Status": item.get("status", "Matched")
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Invoice", "Shop", "Date", "GST", "Total", "Status"])

# ============================================
# EXCEL EXPORT PRO
# ============================================

def export_excel_pro(df):
    output = BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice Summary"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    headers = list(df.columns)
    for col_num, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font

    for row_num, row in enumerate(df.values, start=2):
        for col_num, value in enumerate(row, start=1):
            ws.cell(row=row_num, column=col_num).value = value

    for column in ws.columns:
        ws.column_dimensions[get_column_letter(column[0].column)].width = 25

    wb.save(output)
    output.seek(0)
    return output.getvalue()

# ============================================
# PDF REPORT
# ============================================

def export_pdf_report(df):
    if SimpleDocTemplate is None:
        return None
    pdf_file = BytesIO()
    doc = SimpleDocTemplate(pdf_file)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("AI Invoice Analysis Report", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    story.append(Spacer(1, 20))

    for _, row in df.iterrows():
        story.append(
            Paragraph(
                f"""
                Invoice: {row['Invoice']}<br/>
                Shop: {row['Shop']}<br/>
                Total: ₹{row['Total']}<br/>
                Status: {row['Status']}
                """,
                styles["BodyText"]
            )
        )
        story.append(Spacer(1, 10))

    doc.build(story)
    pdf_file.seek(0)
    return pdf_file.getvalue()

# ============================================
# KPI METRICS
# ============================================

def render_kpi_metrics(df):
    if df.empty:
        return
    total_bills = len(df)
    matched = len(df[df["Status"] == "Matched"])
    mismatch = len(df[df["Status"] == "Mismatch"])
    revenue = df["Total"].sum()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Bills", total_bills)
    with c2:
        st.metric("Matched", matched)
    with c3:
        st.metric("Mismatch", mismatch)
    with c4:
        st.metric("Revenue", f"₹{revenue:,.2f}")

# ============================================
# CHARTS
# ============================================

def render_status_chart(df):
    if px is None or df.empty:
        return
    status_count = df["Status"].value_counts().reset_index()
    status_count.columns = ["Status", "Count"]
    fig = px.pie(status_count, names="Status", values="Count", title="Invoice Status Distribution")
    st.plotly_chart(fig, use_container_width=True)

def render_daily_sales(df):
    if px is None or df.empty or "Date" not in df.columns:
        return
    sales = df.groupby("Date")["Total"].sum().reset_index()
    fig = px.bar(sales, x="Date", y="Total", title="Daily Sales")
    st.plotly_chart(fig, use_container_width=True)

def render_top_vendors(df):
    if px is None or df.empty:
        return
    vendors = df.groupby("Shop")["Total"].sum().reset_index()
    vendors = vendors.sort_values("Total", ascending=False).head(10)
    fig = px.bar(vendors, x="Shop", y="Total", title="Top Vendors")
    st.plotly_chart(fig, use_container_width=True)

def gst_summary(df):
    valid = 0
    invalid = 0
    if "GST" in df.columns:
        for gst in df["GST"]:
            if validate_gst(gst):
                valid += 1
            else:
                invalid += 1
    return {"valid": valid, "invalid": invalid}

def render_analytics_dashboard(df):
    st.header("📊 Analytics Dashboard")
    if df.empty:
        st.info("No logs/data recorded yet.")
        return
    render_kpi_metrics(df)
    st.divider()
    render_status_chart(df)
    st.divider()
    render_daily_sales(df)
    st.divider()
    render_top_vendors(df)

    gst_data = gst_summary(df)
    st.success(f"Valid GST: {gst_data['valid']}")
    st.warning(f"Invalid GST: {gst_data['invalid']}")

# ============================================
# SYSTEM PAGES
# ============================================

def create_backup():
    try:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")
        if os.path.exists(DB_PATH):
            shutil.copy(DB_PATH, backup_file)
            return True
        return False
    except Exception:
        return False

def show_history_page():
    st.header("📜 Processing History")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(str(e))

def show_audit_logs():
    st.header("🔍 Audit Logs")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY id DESC", conn)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(str(e))

def settings_page():
    st.header("⚙️ Settings")
    if st.button("Create Database Backup"):
        if create_backup():
            st.success("Backup Created")
        else:
            st.error("Backup Failed (No database initialized yet)")

def processing_page():
    st.header("🧾 AI Invoice Processor")
    provider = st.selectbox("OCR Provider", ["Gemini", "Google Vision"])
    uploaded_files = st.file_uploader("Upload Files", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

    if st.button("Start Processing"):
        if not uploaded_files:
            st.warning("Upload files first")
            return

        model_bundle = {
            "gemini": setup_gemini(),
            "vision": setup_google_vision(),
            "openai": setup_openai()
        }

        results = process_batch(uploaded_files, provider, model_bundle)
        st.success(f"Processed {len(results)} files successfully!")
        st.session_state.results = results

def dashboard_page():
    if "results" not in st.session_state or not st.session_state.results:
        st.header("📊 Dashboard")
        st.info("No active session data found. Showing historical entries from database:")
        try:
            with sqlite3.connect(DB_PATH) as conn:
                df_db = pd.read_sql_query("SELECT * FROM bills", conn)
            if not df_db.empty:
                # Format to map build_summary_dataframe structural elements
                df_db.columns = ["id", "invoice_number", "shop_name", "bill_date", "gst_number", "total", "calculated_total", "status", "created_at"]
                formatted_results = df_db.to_dict(orient="records")
                df = build_summary_dataframe(formatted_results)
                render_analytics_dashboard(df)
            else:
                st.warning("Database handles are completely clean.")
        except Exception as e:
            st.error(str(e))
        return

    df = build_summary_dataframe(st.session_state.results)
    render_analytics_dashboard(df)

def export_page():
    st.header("📥 Export Center")
    if "results" not in st.session_state or not st.session_state.results:
        st.warning("Nothing found in active buffer to export.")
        return

    df = build_summary_dataframe(st.session_state.results)
    excel_file = export_excel_pro(df)

    st.download_button(
        "Download Excel",
        excel_file,
        file_name="Invoice_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    pdf_file = export_pdf_report(df)
    if pdf_file:
        st.download_button(
            "Download PDF",
            pdf_file,
            file_name="Invoice_Report.pdf",
            mime="application/pdf"
        )

# ============================================
# SIDEBAR NAVIGATION
# ============================================

def sidebar_navigation():
    st.sidebar.title("Deep CSC V2")
    role = st.session_state.get("role", "viewer")

    pages = ["Dashboard", "Invoice Processor", "Export", "History", "Settings"]
    if role == "admin":
        pages.append("Audit Logs")

    return st.sidebar.radio("Navigation", pages)

def logout():
    if st.sidebar.button("Logout"):
        username = st.session_state.get("username", "Unknown")
        log_action(username, "LOGOUT")
        st.session_state.clear()
        st.rerun()

# ============================================
# MAIN APPLICATION ENGINE
# ============================================

def main():
    st.set_page_config(
        page_title="Deep CSC AI Processor V2",
        page_icon="🧾",
        layout="wide"
    )

    init_db()
    init_session()

    if not st.session_state.logged_in:
        login_screen()
        return

    page = sidebar_navigation()
    logout()

    if page == "Dashboard":
        dashboard_page()
    elif page == "Invoice Processor":
        processing_page()
    elif page == "Export":
        export_page()
    elif page == "History":
        show_history_page()
    elif page == "Settings":
        settings_page()
    elif page == "Audit Logs":
        show_audit_logs()

if __name__ == "__main__":
    main()
