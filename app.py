import base64
import json
import re
import sqlite3
import tempfile
import subprocess
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
    WINDOWS_PRINTER_AVAILABLE = False

import warnings
warnings.filterwarnings("ignore")

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"


def secret_or_default(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return default


DEFAULT_USERNAME = secret_or_default("APP_USERNAME", "admin")
DEFAULT_PASSWORD = secret_or_default("APP_PASSWORD", "password123")


def setup_page():
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide", initial_sidebar_state="expanded")


def apply_css():
    st.markdown(
        """
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
        .print-btn { background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important; }
        .scan-btn { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
        "gemini_cooldown_seconds": 900,
        "gemini_retry_count": 0,
        "batch_results": {},
        "perplexity_enabled": True,
        "docai_enabled": True,
        "vision_enabled": True,
        "textract_enabled": True,
        "scanning_active": False,
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
    return boto3.client(
        "textract",
        region_name=secret_or_default("AWS_REGION", "ap-south-1"),
        aws_access_key_id=secret_or_default("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=secret_or_default("AWS_SECRET_ACCESS_KEY"),
    )


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
            cleaned.append(
                {
                    "name": it.get("name") or "",
                    "qty": it.get("qty") or "",
                    "rate": it.get("rate") or "",
                    "amount": it.get("amount") or "",
                }
            )
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
    if client is None:
        raise RuntimeError("OpenAI not configured")
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
    )
    return parse_json_from_response(resp.choices[0].message.content)


def analyze_perplexity(api_key, image):
    if not api_key or requests is None:
        raise RuntimeError("Perplexity not configured")
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
                        "items": {"type": "array"},
                        "total": {"type": ["string", "null"]},
                    },
                    "required": ["shop_name", "bill_date", "gst_number", "items", "total"],
                },
            },
        },
        "temperature": 0.0,
    }
    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    return parse_json_from_response(r.json()["choices"][0]["message"]["content"])


def analyze_google_vision(client, image):
    if client is None:
        raise RuntimeError("Google Vision not configured")
    b = image_to_bytes(image)
    img = vision.Image(content=b)
    resp = client.document_text_detection(image=img)
    text = getattr(resp, "full_text_annotation", None)
    extracted = getattr(text, "text", "") if text else ""
    return heuristic_parse_from_text(extracted)


def analyze_document_ai(image):
    if documentai is None:
        raise RuntimeError("Document AI not configured")
    project_id = secret_or_default("GCP_PROJECT_ID", "").strip()
    location = secret_or_default("DOC_AI_LOCATION", "us")
    processor_id = secret_or_default("DOC_AI_PROCESSOR_ID", "").strip()
    if not project_id or not processor_id:
        raise RuntimeError("Document AI credentials not configured")
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(project_id, location, processor_id)
    content = image_to_bytes(image)
    raw_document = documentai.RawDocument(content=content, mime_type="image/jpeg")
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    result = client.process_document(request=request)
    doc = result.document
    return heuristic_parse_from_text(getattr(doc, "text", "") or "")


def analyze_textract(client, image):
    if client is None:
        raise RuntimeError("Textract not configured")
    img_bytes = image_to_bytes(image)
    resp = client.analyze_expense(Document={"Bytes": img_bytes})
    text_parts = []
    docs = resp.get("ExpenseDocuments", [])
    for d in docs:
        for sf in d.get("SummaryFields", []):
            text_parts.append(f"{sf.get('Type', {}).get('Text', '')}: {sf.get('ValueDetection', {}).get('Text', '')}")
        for g in d.get("LineItemGroups", []):
            for item in g.get("LineItems", []):
                line = []
                for f in item.get("LineItemExpenseFields", []):
                    line.append(f"{f.get('Type', {}).get('Text', '')}={f.get('ValueDetection', {}).get('Text', '')}")
                if line:
                    text_parts.append(" | ".join(line))
    return heuristic_parse_from_text("\n".join(text_parts))


def heuristic_parse_from_text(text):
    text = text or ""
    shop_name = None
    bill_date = None
    gst_number = None
    total = None
    items = []

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if lines:
        shop_name = lines[0][:80]

    m = re.search(r"\bGSTIN[:\s]*([0-9A-Z]{15})\b", text, re.I)
    if m:
        gst_number = m.group(1)

    date_patterns = [r"\b(\d{2}[/-]\d{2}[/-]\d{2,4})\b", r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b"]
    for p in date_patterns:
        m = re.search(p, text)
        if m:
            bill_date = m.group(1)
            break

    total_patterns = [r"\bTotal[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b", r"\bGrand Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b"]
    for p in total_patterns:
        m = re.search(p, text, re.I)
        if m:
            total = m.group(1)
            break

    return {"shop_name": shop_name, "bill_date": bill_date, "gst_number": gst_number, "items": items, "total": total}


def analyze_with_auto_fallback(model_bundle, image):
    provider = st.session_state.get("selected_provider", "Google Vision OCR")
    order = [provider, "Google Vision OCR", "Google Document AI", "AWS Textract", "Gemini", "OpenAI", "Perplexity Verify"]
    seen = set()
    last_err = None

    for p in order:
        if p in seen:
            continue
        seen.add(p)
        try:
            if p == "Google Vision OCR" and model_bundle.get("vision_client") and st.session_state.get("vision_enabled", True):
                return analyze_google_vision(model_bundle["vision_client"], image)

            if p == "Google Document AI" and st.session_state.get("docai_enabled", True):
                return analyze_document_ai(image)

            if p == "AWS Textract" and model_bundle.get("textract_client") and st.session_state.get("textract_enabled", True):
                return analyze_textract(model_bundle["textract_client"], image)

            if p == "Gemini" and model_bundle.get("gemini") and can_try_gemini():
                result = analyze_gemini(model_bundle["gemini"], image)
                st.session_state.gemini_available = True
                st.session_state.last_gemini_error_time = None
                st.session_state.gemini_retry_count = 0
                return result

            if p == "OpenAI" and model_bundle.get("openai"):
                return analyze_openai(model_bundle["openai"], image)

            if p == "Perplexity Verify" and model_bundle.get("perplexity_enabled") and model_bundle.get("perplexity_key"):
                return analyze_perplexity(model_bundle["perplexity_key"], image)

        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if p == "Gemini" and ("429" in msg or "quota" in msg or "rate limit" in msg):
                st.session_state.gemini_available = False
                st.session_state.last_gemini_error_time = datetime.now()
                st.session_state.gemini_retry_count += 1
                continue
            if p == "Perplexity Verify" and ("401" in msg or "unauthorized" in msg or "authentication" in msg):
                st.session_state.perplexity_enabled = False
                continue

    raise RuntimeError(f"All providers failed: {last_err}")


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


def open_windows_scanner():
    try:
        subprocess.Popen(["C:\\Windows\\System32\\WFS.exe"])
        return True, "📷 Windows Fax and Scan opened! Use it to scan"
    except Exception:
        return True, "📷 Open Start Menu → Search 'Scan' → Open Windows Scan app"


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
        else:
            st.warning(print_msg, icon="⚠️")

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
    else:
        st.warning(print_msg, icon="⚠️")


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
    with c3:
        st.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
    with c4:
        st.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")

    if status_txt == "Matched":
        st.success("🎯 Auto-Arithmetic Audit Pass.")
    else:
        st.error(f"🛑 Audit Discrepancy Found: ₹{diff:,.2f}")

    if save_to_db and insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt):
        st.toast("Saved to DB", icon="💾")

    st.markdown("### 🖨️ Print Options")
    pc1, pc2 = st.columns(2)

    with pc1:
        if st.button("🖨️ Direct Print Excel", use_container_width=True, key=f"print_excel_{safe_source}"):
            try:
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Data")
                temp_excel = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                temp_excel.write(buffer.getvalue())
                temp_excel.close()

                print_success, print_msg = print_excel_file(temp_excel.name)
                if print_success:
                    st.success(print_msg)
                else:
                    st.error(print_msg)
            except Exception as e:
                st.error(f"Print failed: {str(e)}")

    with pc2:
        if st.button("📄 Direct Print PDF", use_container_width=True, key=f"print_pdf_{safe_source}"):
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

            print_success, print_msg = print_pdf_file(pdf_temp.name)
            if print_success:
                st.success(print_msg)
            else:
                st.error(print_msg)

    export_payload(df, safe_shop + "_ledger", safe_source)
    export_pdf(shop_name, bill_date, gst_number, bill_total, safe_source)


def build_batch_summary(results):
    rows = []
    for item in results:
        if item.get("data"):
            d = item["data"]
            items = normalize_items(d.get("items"))
            tmp_df = pd.DataFrame(items)
            if not tmp_df.empty:
                tmp_df["amount"] = pd.to_numeric(tmp_df["amount"], errors="coerce").fillna(0)
                calc_total = float(tmp_df["amount"].sum())
            else:
                calc_total = 0.0
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

        st.download_button(
            label,
            data=buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=key,
        )

        print_success, print_msg = print_excel_file(temp_excel.name)
        if print_success:
            st.success(f"🖨️ {print_msg}")

    except Exception:
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download CSV Instead",
            data=csv_data,
            file_name=filename.replace(".xlsx", ".csv"),
            mime="text/csv",
            use_container_width=True,
            key=key + "_csv",
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
        unsafe_allow_html=True,
    )

    printer_ok, printer_msg, printer_type = check_printer_status()

    if printer_ok:
        st.success(f"🖨️ **Printer Ready:** {printer_msg} ✓", icon="✅")
    else:
        if printer_type == "install":
            st.warning(
                "⚠️ **Install Printer Support**\n\n"
                "Run this command in terminal:\n"
                "```bash\npip install pywin32\n```\n\n"
                "Then restart the app.",
                icon="⚠️",
            )
        else:
            st.info(
                f"ℹ️ **Printer Setup**: {printer_msg}\n\n"
                "1. Windows Settings → Devices → Printers & scanners\n"
                "2. Add your Brother printer\n"
                "3. Set as default printer\n"
                "4. Restart app",
                icon="ℹ️",
            )

    if st.button("🖨️ Test Print", use_container_width=True, key="test_print"):
        test_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        doc = SimpleDocTemplate(test_pdf.name)
        styles = getSampleStyleSheet()
        doc.build([Paragraph("Test Print from Deep CSC AI - Bill Processor", styles["Normal"])])
        print_success, print_msg = print_pdf_file(test_pdf.name)
        if print_success:
            st.success(print_msg)
        else:
            st.error(print_msg)

    if st.button("📷 Open Scanner App", use_container_width=True, key="open_scanner", type="primary"):
        scan_success, scan_msg = open_windows_scanner()
        if scan_success:
            st.success(scan_msg)
            st.info("⬆️ After scanning, upload the image below to process it automatically", icon="ℹ️")
        else:
            st.error(scan_msg)

    providers = ["Google Vision OCR", "Google Document AI", "AWS Textract", "Gemini", "OpenAI", "Perplexity Verify"]
    st.session_state.selected_provider = st.selectbox("Select OCR Provider", providers, index=0)

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
        "perplexity_enabled": st.session_state.get("perplexity_enabled", True),
    }

    uploaded_file = st.file_uploader("Upload Bill Image or PDF", type=["jpg", "jpeg", "png", "pdf"])

    if uploaded_file:
        file_bytes = uploaded_file.read()
        file_name = uploaded_file.name.lower()

        if file_name.endswith(".pdf"):
            if st.button("Process PDF", use_container_width=True):
                results = process_pdf_pages(model_bundle, file_bytes, uploaded_file.name)
                df = build_batch_summary(results)
                st.dataframe(df, use_container_width=True, hide_index=True)
                make_excel_download(df, "batch_summary.xlsx")
        else:
            image = Image.open(BytesIO(file_bytes)).convert("RGB")
            st.image(image, caption="Uploaded Bill", use_container_width=True)
            if st.button("Process Image", use_container_width=True):
                data = analyze_with_auto_fallback(model_bundle, image)
                render_bill_result(data, uploaded_file.name, save_to_db=True)


def main():
    setup_page()
    apply_css()
    init_db()
    init_auth()
    init_runtime_state()

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
        st.write("Provider-ready OCR and invoice extraction dashboard.")
        if st.button("Logout", use_container_width=True):
            terminate_session()

    render_upload_module({
        "vision_client": setup_google_vision(),
        "gemini": setup_gemini(),
        "openai": setup_openai(),
        "textract_client": setup_textract(),
        "perplexity_key": secret_or_default("PERPLEXITY_API_KEY", "").strip(),
        "perplexity_enabled": st.session_state.get("perplexity_enabled", True),
    })


if __name__ == "__main__":
    main()
