import base64
import json
import re
import sqlite3
import tempfile
import os
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

try:
    from pdf2image import convert_from_bytes
except Exception:
    convert_from_bytes = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import requests
except Exception:
    requests = None

try:
    from google.cloud import vision
except Exception:
    vision = None

try:
    from google.cloud import documentai
except Exception:
    documentai = None

try:
    import boto3
except Exception:
    boto3 = None

try:
    import win32print
    WINDOWS_PRINTER_AVAILABLE = True
except Exception:
    win32print = None
    WINDOWS_PRINTER_AVAILABLE = False

import warnings
warnings.filterwarnings("ignore")

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
MAX_PDF_PAGES = 1
PDF_DPI = 200
PROCESSING_TIMEOUT_SECONDS = 30


def secret_or_default(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return default


DEFAULT_USERNAME = secret_or_default("APP_USERNAME", "admin")
DEFAULT_PASSWORD = secret_or_default("APP_PASSWORD", "password123")


def setup_page():
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide", initial_sidebar_state="expanded")


def init_db():
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute(
            """
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
            """
        )


def init_auth():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False


def init_runtime_state():
    defaults = {
        "selected_provider": "Google Vision OCR",
        "gemini_available": True,
        "last_gemini_error_time": None,
        "gemini_cooldown_seconds": 120,
        "gemini_retry_count": 0,
        "perplexity_enabled": False,
        "docai_enabled": False,
        "vision_enabled": True,
        "textract_enabled": False,
        "selected_printer": None,
        "printer_refresh_nonce": 0,
        "theme_mode": "light",
        "history_search": "",
        "history_shop": "",
        "history_gst": "",
        "history_status": "All",
        "history_min_amount": "",
        "history_max_amount": "",
        "history_date_from": None,
        "history_date_to": None,
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


def apply_theme_css():
    if st.session_state.theme_mode == "dark":
        st.markdown("<style>.stApp { background: #0b1220; color: #e5e7eb; } section[data-testid='stSidebar'] { background: #0f172a; } .stDataFrame, .stMarkdown, .stText, .stMetricValue, .stMetricLabel { color: #e5e7eb !important; } div[data-testid='stMetricValue'] { color: #f8fafc !important; } div[data-testid='stMetricLabel'] { color: #cbd5e1 !important; }</style>", unsafe_allow_html=True)
    else:
        st.markdown("<style>.stApp { background: #f8fafc; color: #0f172a; } section[data-testid='stSidebar'] { background: #0f172a; }</style>", unsafe_allow_html=True)


def apply_css():
    st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    h1, h2, h3, h4 { font-family: system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
    .deep-csc-header { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%); padding: 30px; border-radius: 24px; margin-bottom: 20px; border: 1px solid rgba(255, 255, 255, 0.1); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; }
    .branding-text h1 { background: linear-gradient(to right, #38bdf8, #c084fc, #f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0; font-size: 34px !important; letter-spacing: -0.5px; }
    .csc-meta-badge { background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.15); padding: 10px 18px; border-radius: 14px; color: #e2e8f0 !important; font-size: 13px !important; line-height: 1.6; }
    .branding-badge { background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); color: white !important; padding: 8px 18px; border-radius: 50px; font-size: 13px !important; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 4px 14px rgba(236, 72, 153, 0.4); }
    .stButton>button { background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important; color: white !important; font-weight: 700 !important; padding: 12px 24px !important; border-radius: 12px !important; border: none !important; }
    </style>
    """, unsafe_allow_html=True)


@st.cache_resource
def setup_gemini():
    if genai is None:
        return None
    api_key = secret_or_default("GEMINI_API_KEY", "").strip()
    if not api_key or "your_" in api_key.lower():
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


@st.cache_resource
def setup_openai():
    api_key = secret_or_default("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None or "your_" in api_key.lower():
        return None
    return OpenAI(api_key=api_key)


@st.cache_resource
def setup_google_vision():
    if vision is None:
        return None
    return vision.ImageAnnotatorClient()


@st.cache_resource
def setup_textract():
    if boto3 is None:
        return None
    if not secret_or_default("AWS_ACCESS_KEY_ID", "") or not secret_or_default("AWS_SECRET_ACCESS_KEY", ""):
        return None
    return boto3.client("textract", region_name=secret_or_default("AWS_REGION", "ap-south-1"), aws_access_key_id=secret_or_default("AWS_ACCESS_KEY_ID"), aws_secret_access_key=secret_or_default("AWS_SECRET_ACCESS_KEY"))


def validate_gst(gst_str):
    if not gst_str:
        return False, "N/A"
    gst_regex = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    clean_gst = re.sub(r"[^A-Z0-9]", "", str(gst_str).upper())
    return bool(re.match(gst_regex, clean_gst)), clean_gst


def normalize_items(items):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for it in items:
        if isinstance(it, dict):
            cleaned.append({"name": it.get("name") or "", "qty": it.get("qty") or "", "rate": it.get("rate") or "", "amount": it.get("amount") or ""})
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
    cooldown = st.session_state.get("gemini_cooldown_seconds", 120)
    return (datetime.now() - last_error).total_seconds() >= cooldown


def build_schema_prompt():
    return """
You are a document extraction specialist.
Return ONLY valid JSON:
{
  "shop_name": null or string,
  "bill_date": null or string,
  "gst_number": null or string,
  "items": [{"name": string, "qty": string, "rate": string, "amount": string}],
  "total": null or string
}
Rules:
- Use visible text only.
- If missing, return null.
- No markdown.
- No explanation.
"""


def image_to_bytes(image):
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def analyze_gemini(model, image):
    resp = model.generate_content([build_schema_prompt(), image])
    return parse_json_from_response(getattr(resp, "text", ""))


def analyze_openai(client, image):
    b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
    resp = client.chat.completions.create(
        model=secret_or_default("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": build_schema_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract invoice JSON from this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ],
        response_format={"type": "json_object"},
        timeout=PROCESSING_TIMEOUT_SECONDS,
    )
    return parse_json_from_response(resp.choices[0].message.content)


def analyze_perplexity(api_key, image):
    b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
    payload = {
        "model": secret_or_default("PERPLEXITY_MODEL", "sonar-pro"),
        "messages": [
            {"role": "system", "content": build_schema_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract invoice JSON from this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ],
        "temperature": 0.0,
    }
    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=PROCESSING_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    return parse_json_from_response(r.json()["choices"][0]["message"]["content"])


def analyze_google_vision(client, image):
    b = image_to_bytes(image)
    img = vision.Image(content=b)
    resp = client.document_text_detection(image=img)
    text = getattr(resp, "full_text_annotation", None)
    extracted = getattr(text, "text", "") if text else ""
    return heuristic_parse_from_text(extracted)


def analyze_document_ai(image):
    project_id = secret_or_default("GCP_PROJECT_ID", "").strip()
    location = secret_or_default("DOC_AI_LOCATION", "us")
    processor_id = secret_or_default("DOC_AI_PROCESSOR_ID", "").strip()
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(project_id, location, processor_id)
    content = image_to_bytes(image)
    raw_document = documentai.RawDocument(content=content, mime_type="image/jpeg")
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    result = client.process_document(request=request)
    return heuristic_parse_from_text(getattr(result.document, "text", "") or "")


def analyze_textract(client, image):
    img_bytes = image_to_bytes(image)
    resp = client.analyze_expense(Document={"Bytes": img_bytes})
    text_parts = []
    for d in resp.get("ExpenseDocuments", []):
        for sf in d.get("SummaryFields", []):
            text_parts.append(f"{sf.get('Type', {}).get('Text', '')}: {sf.get('ValueDetection', {}).get('Text', '')}")
    return heuristic_parse_from_text("\n".join(text_parts))


def heuristic_parse_from_text(text):
    text = text or ""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    shop_name = lines[0][:80] if lines else None
    gst_number = None
    bill_date = None
    total = None
    m = re.search(r"\bGSTIN[:\s]*([0-9A-Z]{15})\b", text, re.I)
    if m:
        gst_number = m.group(1)
    for p in [r"\b(\d{2}[/-]\d{2}[/-]\d{2,4})\b", r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b"]:
        m = re.search(p, text)
        if m:
            bill_date = m.group(1)
            break
    for p in [r"\bTotal[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b", r"\bGrand Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b"]:
        m = re.search(p, text, re.I)
        if m:
            total = m.group(1)
            break
    return {"shop_name": shop_name, "bill_date": bill_date, "gst_number": gst_number, "items": [], "total": total}


def analyze_with_auto_fallback(model_bundle, image):
    provider = st.session_state.get("selected_provider", "Google Vision OCR")

    if provider == "Google Vision OCR" and model_bundle.get("vision_client") and st.session_state.get("vision_enabled", True):
        return analyze_google_vision(model_bundle["vision_client"], image)

    if provider == "Google Document AI" and st.session_state.get("docai_enabled", False):
        return analyze_document_ai(image)

    if provider == "AWS Textract" and model_bundle.get("textract_client") and st.session_state.get("textract_enabled", False):
        return analyze_textract(model_bundle["textract_client"], image)

    if provider == "Gemini" and model_bundle.get("gemini") and can_try_gemini():
        try:
            result = analyze_gemini(model_bundle["gemini"], image)
            st.session_state.gemini_available = True
            st.session_state.last_gemini_error_time = None
            st.session_state.gemini_retry_count = 0
            return result
        except Exception as e:
            st.session_state.gemini_available = False
            st.session_state.last_gemini_error_time = datetime.now()
            st.session_state.gemini_retry_count += 1
            raise e

    if provider == "OpenAI" and model_bundle.get("openai"):
        return analyze_openai(model_bundle["openai"], image)

    if provider == "Perplexity Verify" and model_bundle.get("perplexity_key") and st.session_state.get("perplexity_enabled", False):
        return analyze_perplexity(model_bundle["perplexity_key"], image)

    raise RuntimeError(f"Provider not available or disabled: {provider}")


def check_printer_status():
    if sys.platform != "win32":
        return False, "Windows only feature", "windows"
    if not WINDOWS_PRINTER_AVAILABLE:
        return False, "Install pywin32: pip install pywin32", "install"
    try:
        default_printer = win32print.GetDefaultPrinter()
        if default_printer:
            return True, default_printer, "ready"
        return False, "No printer installed in Windows", "none"
    except Exception as e:
        return False, str(e), "error"


def get_windows_printers():
    if sys.platform != "win32" or win32print is None:
        return []
    return [p[2] for p in win32print.EnumPrinters(2)]


def get_default_printer():
    if sys.platform != "win32" or win32print is None:
        return None
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def render_printer_status_card():
    ok, msg, kind = check_printer_status()
    if ok:
        st.markdown(f"<div style='padding:14px;border-radius:14px;background:#ecfdf5;border:1px solid #10b981;margin-bottom:12px;'><b style='color:#047857;'>🟢 Printer Ready</b><br><span style='color:#065f46;'>{msg}</span></div>", unsafe_allow_html=True)
    else:
        color = "#f59e0b" if kind == "install" else "#ef4444"
        label = "🟡 Printer Setup Needed" if kind == "install" else "🔴 Printer Not Ready"
        st.markdown(f"<div style='padding:14px;border-radius:14px;background:#fff7ed;border:1px solid {color};margin-bottom:12px;'><b style='color:{color};'>{label}</b><br><span style='color:#7c2d12;'>{msg}</span></div>", unsafe_allow_html=True)


def render_printer_selector():
    if sys.platform != "win32" or win32print is None:
        st.info("Windows only feature")
        return None
    if st.button("🔄 Refresh printer list", key="refresh_printers"):
        st.session_state.printer_refresh_nonce += 1
        st.rerun()
    printers = get_windows_printers()
    if not printers:
        st.warning("No printers found.")
        return None
    default_printer = get_default_printer()
    if "selected_printer" not in st.session_state or st.session_state.selected_printer not in printers:
        st.session_state.selected_printer = default_printer if default_printer in printers else printers[0]
    selected_printer = st.selectbox("Select Printer", printers, index=printers.index(st.session_state.selected_printer), key=f"printer_selector_{st.session_state.printer_refresh_nonce}")
    st.session_state.selected_printer = selected_printer
    st.caption(f"Current default printer: {default_printer or 'Not set'}")
    if st.button("Set as Default Printer", use_container_width=True, key="set_default_printer"):
        try:
            win32print.SetDefaultPrinter(selected_printer)
            st.success(f"Default printer set to: {selected_printer}")
        except Exception as e:
            st.error(f"Failed to set default printer: {e}")
    return selected_printer


def add_history_table(limit=50):
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        return pd.read_sql_query(
            f"""
            SELECT shop_name, bill_date, gst_number, total, calculated_total, status, timestamp
            FROM bills
            ORDER BY id DESC
            LIMIT {int(limit)}
            """,
            conn,
        )


def filter_history(df):
    if df.empty:
        return df
    out = df.copy()
    if st.session_state.history_search:
        q = st.session_state.history_search.lower()
        mask = (
            out["shop_name"].astype(str).str.lower().str.contains(q, na=False)
            | out["gst_number"].astype(str).str.lower().str.contains(q, na=False)
            | out["status"].astype(str).str.lower().str.contains(q, na=False)
        )
        out = out[mask]
    if st.session_state.history_shop:
        out = out[out["shop_name"].astype(str).str.lower().str.contains(st.session_state.history_shop.lower(), na=False)]
    if st.session_state.history_gst:
        out = out[out["gst_number"].astype(str).str.lower().str.contains(st.session_state.history_gst.lower(), na=False)]
    if st.session_state.history_status != "All":
        out = out[out["status"] == st.session_state.history_status]
    if st.session_state.history_min_amount:
        out = out[pd.to_numeric(out["total"], errors="coerce").fillna(0) >= safe_float(st.session_state.history_min_amount)]
    if st.session_state.history_max_amount:
        out = out[pd.to_numeric(out["total"], errors="coerce").fillna(0) <= safe_float(st.session_state.history_max_amount)]
    if st.session_state.history_date_from:
        out = out[out["bill_date"].astype(str) >= str(st.session_state.history_date_from)]
    if st.session_state.history_date_to:
        out = out[out["bill_date"].astype(str) <= str(st.session_state.history_date_to)]
    return out


def render_print_preview(shop_name, bill_date, gst_number, bill_total, items_df):
    with st.expander("🖨️ Print Preview", expanded=False):
        st.write(f"**Shop:** {shop_name}")
        st.write(f"**Date:** {bill_date}")
        st.write(f"**GSTIN:** {gst_number}")
        st.write(f"**Total:** ₹{bill_total:,.2f}")
        if not items_df.empty:
            st.dataframe(items_df, use_container_width=True, hide_index=True)
        else:
            st.info("No items to preview.")


def print_excel_file(file_path):
    try:
        if sys.platform == "win32":
            os.startfile(file_path, "print")
            return True, "🖨️ Print job sent to default printer! ✓"
        return False, "Windows only feature"
    except Exception as e:
        return False, f"Print failed: {str(e)}"


def print_pdf_file(file_path):
    try:
        if sys.platform == "win32":
            os.startfile(file_path, "print")
            return True, "🖨️ Print job sent to default printer! ✓"
        return False, "Windows only feature"
    except Exception as e:
        return False, f"Print failed: {str(e)}"


def open_naps2_scanner():
    if sys.platform != "win32":
        return False, "Windows only feature"
    naps2_paths = [
        r"C:\Program Files\NAPS2\NAPS2.exe",
        r"C:\Program Files (x86)\NAPS2\NAPS2.exe",
        r"C:\Program Files\NAPS2\naps2.exe",
        r"C:\Program Files (x86)\NAPS2\naps2.exe",
    ]
    for p in naps2_paths:
        if Path(p).exists():
            os.startfile(p)
            return True, f"Scanner opened: {p}"
    return False, "NAPS2 not installed. Please install it first."


def show_printer_setup_notice():
    if sys.platform == "win32":
        st.info(
            "ℹ️ Printer Setup: Windows only feature\n"
            "1. Open Windows Settings → Bluetooth & devices → Printers & scanners\n"
            "2. Add your printer\n"
            "3. Set it as default printer\n"
            "4. Restart the app",
            icon="ℹ️",
        )
    else:
        st.info("ℹ️ Printer Setup: Windows only feature", icon="ℹ️")


def insert_bill(shop, date, gst, total, calc_total, status):
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO bills
            (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        return cur.rowcount > 0


def export_payload(df, base_name, widget_key):
    try:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        temp_excel = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_excel.write(buffer.getvalue())
        temp_excel.close()
        st.download_button(
            "📥 Export Excel Data Sheets",
            data=buffer.getvalue(),
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"excel_{widget_key}",
        )
        print_success, print_msg = print_excel_file(temp_excel.name)
        if print_success:
            st.success(print_msg, icon="🖨️")
    except Exception:
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download CSV Instead",
            data=csv_data,
            file_name=f"{base_name}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"csv_{widget_key}",
        )


def export_pdf(shop_name, bill_date, gst_number, bill_total, widget_key):
    pdf_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(pdf_temp.name)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"Invoice Summary: {shop_name}", styles["Title"]),
        Spacer(1, 10),
        Paragraph(f"Date: {bill_date} | GSTIN: {gst_number}", styles["Normal"]),
        Paragraph(f"Verified Final Amount: INR {bill_total:.2f}", styles["Heading3"]),
    ]
    doc.build(elements)
    with open(pdf_temp.name, "rb") as f:
        st.download_button(
            "📄 Download Sign-off PDF",
            f.read(),
            file_name=f"{re.sub(r'[^A-Za-z0-9_-]+', '_', shop_name)}_receipt.pdf",
            mime="application/pdf",
            use_container_width=True,
            key=f"pdf_{widget_key}",
        )
    print_success, print_msg = print_pdf_file(pdf_temp.name)
    if print_success:
        st.success(print_msg, icon="🖨️")


def render_bill_result(data, source_name, save_to_db=False):
    if not isinstance(data, dict):
        st.error("AI se data nahi mil paaya.")
        return
    shop_name = str(data.get("shop_name") or "Unknown Shop").strip()
    bill_date = str(data.get("bill_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    gst_number = data.get("gst_number") or "N/A"
    safe_shop = re.sub(r"[^A-Za-z0-9_-]+", "_", shop_name)
    safe_source = re.sub(r"[^A-Za-z0-9_-]+", "_", str(source_name))
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
    c3, c4 = st.columns(2)
    c3.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
    c4.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")
    if status_txt == "Matched":
        st.success("🎯 Auto-Arithmetic Audit Pass.")
    else:
        st.error(f"🛑 Audit Discrepancy Found: ₹{diff:,.2f}")
    render_printer_status_card()
    render_print_preview(shop_name, bill_date, gst_number, bill_total, df)
    if save_to_db and insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt):
        st.toast("Saved to DB", icon="💾")
    export_payload(df, safe_shop + "_ledger", safe_source)
    export_pdf(shop_name, bill_date, gst_number, bill_total, safe_source)


def build_batch_summary(results):
    rows = []
    for item in results:
        if item.get("data"):
            d = item["data"]
            items = normalize_items(d.get("items"))
            tmp_df = pd.DataFrame(items)
            calc_total = float(pd.to_numeric(tmp_df["amount"], errors="coerce").fillna(0).sum()) if not tmp_df.empty else 0.0
            total = safe_float(d.get("total", 0))
            rows.append(
                {
                    "page": item.get("page"),
                    "source": item.get("source"),
                    "shop_name": str(d.get("shop_name") or "Unknown Shop").strip(),
                    "bill_date": str(d.get("bill_date") or datetime.now().strftime("%Y-%m-%d")).strip(),
                    "gst_number": d.get("gst_number") or "N/A",
                    "bill_total": total,
                    "calculated_total": calc_total,
                    "difference": abs(calc_total - total),
                    "status": "Matched" if abs(calc_total - total) < 1 else "Mismatch",
                }
            )
        else:
            rows.append(
                {
                    "page": item.get("page"),
                    "source": item.get("source"),
                    "shop_name": None,
                    "bill_date": None,
                    "gst_number": None,
                    "bill_total": None,
                    "calculated_total": None,
                    "difference": None,
                    "status": f"Error: {item.get('error')}",
                }
            )
    return pd.DataFrame(rows)


def make_excel_download(df, filename, label="📥 Download Excel", key="excel_download"):
    try:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Batch Summary")
        temp_excel = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_excel.write(buffer.getvalue())
        temp_excel.close()
        st.download_button(label, data=buffer.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=key)
        print_success, print_msg = print_excel_file(temp_excel.name)
        if print_success:
            st.success(f"🖨️ {print_msg}")
    except Exception:
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV Instead", data=csv_data, file_name=filename.replace(".xlsx", ".csv"), mime="text/csv", use_container_width=True, key=key + "_csv")


def render_theme_toggle():
    mode = st.radio("Theme", ["light", "dark"], horizontal=True, index=0 if st.session_state.theme_mode == "light" else 1)
    if mode != st.session_state.theme_mode:
        st.session_state.theme_mode = mode
        st.rerun()


def render_upload_module():
    st.markdown(
        """
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by multiple providers.</p>
            </div>
            <div class="csc-meta-badge">📍 <b>Deep Digital Seva Kendra</b><br>👤 Owner: Deepak | ID: 256423250015</div>
            <div class="branding-badge">Deep CSC AI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["📷 Scan / Upload", "🖨️ Preview", "🕘 History", "⚙️ Settings"])

    with tabs[0]:
        show_printer_setup_notice()
        render_printer_status_card()
        render_printer_selector()

        if st.button("📷 Open Scanner App", use_container_width=True, key="open_scanner", type="primary"):
            scan_success, scan_msg = open_naps2_scanner()
            if scan_success:
                st.success(scan_msg)
                st.info("After scanning, upload the saved image/PDF back into the app.", icon="ℹ️")
            else:
                st.error(scan_msg)

        providers = ["Google Vision OCR", "Google Document AI", "AWS Textract", "Gemini", "OpenAI", "Perplexity Verify"]
        st.session_state.selected_provider = st.selectbox("Select OCR Provider", providers, index=0)

        uploaded_file = st.file_uploader("Upload Bill Image or PDF", type=["jpg", "jpeg", "png", "pdf"])

        vision_client = setup_google_vision()
        gemini_model = setup_gemini()
        openai_client = setup_openai()
        textract_client = setup_textract()
        perplexity_key = secret_or_default("PERPLEXITY_API_KEY", "").strip()

        model_bundle = {
            "vision_client": vision_client,
            "gemini": gemini_model,
            "openai": openai_client,
            "textract_client": textract_client,
            "perplexity_key": perplexity_key,
        }

        if uploaded_file:
            file_bytes = uploaded_file.read()
            file_name = uploaded_file.name.lower()

            if file_name.endswith(".pdf"):
                if st.button("Process PDF", use_container_width=True):
                    if convert_from_bytes is None:
                        st.error("pdf2image not installed.")
                    else:
                        pages = convert_from_bytes(file_bytes, dpi=PDF_DPI)[:MAX_PDF_PAGES]
                        results = []
                        for idx, page_img in enumerate(pages, start=1):
                            try:
                                data = analyze_with_auto_fallback(model_bundle, page_img)
                                results.append({"page": idx, "source": uploaded_file.name, "data": data, "error": None})
                            except Exception as e:
                                results.append({"page": idx, "source": uploaded_file.name, "data": None, "error": str(e)})
                        df = build_batch_summary(results)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        make_excel_download(df, "batch_summary.xlsx")
            else:
                image = Image.open(BytesIO(file_bytes)).convert("RGB")
                st.image(image, caption="Uploaded Bill", use_container_width=True)
                if st.button("Process Image", use_container_width=True):
                    data = analyze_with_auto_fallback(model_bundle, image)
                    render_bill_result(data, uploaded_file.name, save_to_db=True)

    with tabs[1]:
        st.subheader("Print Preview")
        st.info("Preview shows after processing an image or PDF in the Scan / Upload tab.", icon="ℹ️")

    with tabs[2]:
        st.subheader("Search & Filter History")
        c1, c2, c3 = st.columns(3)
        st.session_state.history_search = c1.text_input("Search all", value=st.session_state.history_search)
        st.session_state.history_shop = c2.text_input("Shop name", value=st.session_state.history_shop)
        st.session_state.history_gst = c3.text_input("GSTIN", value=st.session_state.history_gst)

        c4, c5, c6 = st.columns(3)
        st.session_state.history_status = c4.selectbox("Status", ["All", "Matched", "Mismatch"], index=["All", "Matched", "Mismatch"].index(st.session_state.history_status))
        st.session_state.history_min_amount = c5.text_input("Min amount", value=st.session_state.history_min_amount)
        st.session_state.history_max_amount = c6.text_input("Max amount", value=st.session_state.history_max_amount)

        c7, c8 = st.columns(2)
        st.session_state.history_date_from = c7.date_input("Date from", value=st.session_state.history_date_from)
        st.session_state.history_date_to = c8.date_input("Date to", value=st.session_state.history_date_to)

        history_df = add_history_table()
        filtered = filter_history(history_df)

        st.markdown("### Recent History")
        if not filtered.empty:
            st.dataframe(filtered, use_container_width=True, hide_index=True)
            csv_bytes = filtered.to_csv(index=False).encode("utf-8")
            st.download_button("Download Filtered CSV", data=csv_bytes, file_name="filtered_history.csv", mime="text/csv", use_container_width=True)
        else:
            st.info("No matching records found.")

    with tabs[3]:
        st.subheader("Settings")
        render_theme_toggle()
        with st.expander("Advanced options", expanded=False):
            st.write("Use this section later for more controls like OCR provider defaults, print shortcuts, or theme tuning.")


def main():
    setup_page()
    init_db()
    init_auth()
    init_runtime_state()
    apply_theme_css()
    apply_css()

    if not st.session_state.logged_in:
        do_login()

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand-box">
                <div class="sidebar-title">Deep CSC</div>
                <div class="sidebar-subtitle">AI Bill Processor</div>
                <div class="sidebar-id-badge">ID: 256423250015</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_theme_toggle()
        st.write("Provider-ready OCR and invoice extraction dashboard.")
        if st.button("Logout", use_container_width=True):
            terminate_session()

    render_upload_module()


if __name__ == "__main__":
    main()
