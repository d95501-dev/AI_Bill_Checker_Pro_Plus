import base64
import json
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

try:
    import fitz
except Exception:
    fitz = None

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

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
    from google.cloud import vision
except Exception:
    vision = None

try:
    import boto3
except Exception:
    boto3 = None

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except Exception:
    service_account = None
    build = None
    MediaFileUpload = None

import warnings
warnings.filterwarnings("ignore")

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
                UNIQUE(shop_name, bill_date, total) ON CONFLICT REPLACE
            )
            """
        )

def init_auth():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def init_runtime_state():
    defaults = {
        "selected_provider": "Gemini",
        "theme_mode": "light",
        "processed_files": set(),
        "gemini_available": True,
        "last_gemini_error_time": None,
        "gemini_cooldown_seconds": 900,
        "current_results": []
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def do_login():
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
        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password Credentials")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

def terminate_session():
    st.session_state.logged_in = False
    for k in list(st.session_state.keys()):
        if k != "logged_in":
            del st.session_state[k]
    st.rerun()

def apply_theme_css():
    theme_mode = st.session_state.get("theme_mode", "light")
    if theme_mode == "dark":
        st.markdown("""
            <style>
            .stApp { background: #0b1220; color: #e5e7eb; }
            section[data-testid="stSidebar"] { background: #0f172a; }
            section[data-testid="stSidebar"] * { color: #f8fafc !important; }
            .stButton>button { background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important; color: white !important; }
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
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.22);
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
            text-transform: uppercase;
        }
        .csc-meta-badge {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            color: #e2e8f0 !important;
            padding: 12px 16px;
            border-radius: 16px;
            font-size: 13px !important;
        }
        .metric-card {
            background: rgba(255,255,255,0.82);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 22px;
            padding: 18px 20px;
            box-shadow: 0 14px 35px rgba(15, 23, 42, 0.10);
        }
        .metric-label { color: #64748b; font-size: 13px; margin-bottom: 8px; }
        .metric-value { font-size: 28px; font-weight: 800; color: #0f172a; }
        .metric-sub { color: #64748b; font-size: 13px; }
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
            border-radius: 14px !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px; background: rgba(255,255,255,0.55); padding: 8px; border-radius: 18px;
        }
        .stTabs [data-baseweb="tab"] { border-radius: 14px; padding: 10px 18px; font-weight: 700; }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #0f172a 0%, #4338ca 100%) !important; color: white !important;
        }
        div[data-testid="stDataFrame"] { border-radius: 18px; overflow: hidden; }
        section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0f172a 0%, #111827 100%); }
        section[data-testid="stSidebar"] * { color: #f8fafc !important; }
        .block-container { padding-top: 1.1rem; padding-bottom: 2rem; }
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
    c1, c2, c3, c4 = st.columns(4)
    total_files = len(df) if df is not None and not df.empty else 0
    matched = int((df["status"] == "Matched").sum()) if total_files else 0
    mismatch = int((df["status"] == "Mismatch").sum()) if total_files else 0
    review = int((df["status"] == "Needs Review").sum()) if total_files else 0

    with c1:
        metric_card("Files Processed", total_files, "Uploaded this session")
    with c2:
        metric_card("Matched Bills", matched, "Auto verified")
    with c3:
        metric_card("Mismatch / Review", mismatch + review, "Needs attention")
    with c4:
        metric_card("OCR Provider", st.session_state.get("selected_provider", "Gemini"), "Current mode")

@st.cache_resource
def setup_gemini():
    if genai is None:
        return None
    api_key = secret_or_default("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

@st.cache_resource
def setup_openai():
    api_key = secret_or_default("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)

@st.cache_resource
def setup_perplexity():
    api_key = secret_or_default("PERPLEXITY_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

@st.cache_resource
def setup_google_vision():
    return vision.ImageAnnotatorClient() if vision is not None else None

def get_drive_service():
    service_account_file = secret_or_default("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if service_account is None or build is None or not os.path.exists(service_account_file):
        return None
    creds = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def upload_to_drive(local_path, drive_name=None, mime_type="application/octet-stream"):
    folder_id = secret_or_default("DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        return None
    service = get_drive_service()
    if service is None or MediaFileUpload is None:
        return None
    metadata = {"name": drive_name or os.path.basename(local_path), "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    return service.files().create(body=metadata, media_body=media, fields="id, name, webViewLink").execute()

def validate_gst(gst_str):
    if not gst_str:
        return False, "N/A"
    gst_regex = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    clean_gst = re.sub(r"[^A-Z0-9]", "", str(gst_str).upper())
    return bool(re.match(gst_regex, clean_gst)), clean_gst

def normalize_items(items):
    if not isinstance(items, list):
        return []
    cleaned = []
    for it in items:
        if isinstance(it, dict):
            cleaned.append({
                "name": it.get("name") or "Unknown Item",
                "qty": it.get("qty") or "1",
                "rate": it.get("rate") or "0",
                "amount": it.get("amount") or "0"
            })
    return cleaned

def parse_json_from_response(response_text):
    raw = (response_text or "").strip().replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    return json.loads(raw)

def safe_float(value):
    if not value:
        return 0.0
    try:
        return float(str(value).replace("₹", "").replace(",", "").strip())
    except Exception:
        return 0.0

def can_try_gemini():
    if st.session_state.get("gemini_available", True):
        return True
    last_error = st.session_state.get("last_gemini_error_time")
    return (not last_error) or ((datetime.now() - last_error).total_seconds() >= st.session_state.get("gemini_cooldown_seconds", 900))

def is_gemini_quota_error(err):
    msg = str(err).lower()
    return ("429" in msg) or ("quota" in msg) or ("resource_exhausted" in msg) or ("rate limit" in msg)

def build_schema_prompt():
    return """
You are a expert invoice extraction specialist. 
Return ONLY a valid JSON object matching the schema below. 
Do not include any explanation or backticks.

{
  "shop_name": string or null,
  "bill_date": string or null,
  "gst_number": string or null,
  "items": [{"name": string, "qty": string, "rate": string, "amount": string}],
  "total": string or null
}

Rules:
1. "items" must list every single product/service transaction detail visible. 
2. Ensure you extract the item names (English or Hindi translation if clear), quantity, rate, and total amount for each row item.
3. Calculate or copy accurate amount per item row.
"""

def image_to_bytes(image):
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def preprocess_for_ocr(image):
    try:
        import cv2
        import numpy as np
        img = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        return Image.fromarray(thresh)
    except Exception:
        return image

def convert_pdf_to_images(file_bytes):
    if fitz is not None:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        doc.close()
        return images
    if pdfium is not None:
        pdf = pdfium.PdfDocument(file_bytes)
        images = []
        for i in range(len(pdf)):
            images.append(pdf[i].render(scale=3).to_pil().convert("RGB"))
        return images
    if convert_from_bytes is not None:
        return convert_from_bytes(file_bytes, dpi=300)
    raise RuntimeError("No PDF rendering library available.")

def extract_vision_text(vision_client, image):
    img = vision.Image(content=image_to_bytes(image))
    resp = vision_client.document_text_detection(image=img)
    text = ""
    if getattr(resp, "full_text_annotation", None):
        text = getattr(resp.full_text_annotation, "text", "") or ""
    if not text.strip() and getattr(resp, "text_annotations", None):
        anns = resp.text_annotations
        if anns and getattr(anns[0], "description", ""):
            text = anns[0].description.strip()
    return text.strip()

def heuristic_extract_items(text):
    items = []
    for ln in [x.strip() for x in (text or "").splitlines() if x.strip()]:
        if re.search(r"\b(invoice|bill|gst|date|total|amount|tax)\b", ln, re.I):
            continue
        m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$", ln)
        if m:
            items.append({"name": m.group(1).strip(), "qty": m.group(2), "rate": m.group(3), "amount": m.group(4)})
    return items[:30]

def heuristic_parse_from_text(text):
    text = (text or "").strip()
    if not text:
        return {"shop_name": None, "bill_date": None, "gst_number": None, "items": [], "total": None, "raw_text": ""}

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    shop_name = None
    for ln in lines[:12]:
        if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax)\b", ln, re.I):
            shop_name = ln[:80]
            break

    gst_number = None
    bill_date = None
    total = None

    gst_patterns = [
        r"\bGSTIN[:\s-]*([0-9A-Z]{15})\b",
        r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"
    ]
    for p in gst_patterns:
        m = re.search(p, text, re.I)
        if m:
            gst_number = m.group(1)
            break

    date_patterns = [
        r"\b(\d{2}[/-]\d{2}[/-]\d{2,4})\b",
        r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b",
        r"\b(\d{2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"
    ]
    for p in date_patterns:
        m = re.search(p, text)
        if m:
            bill_date = m.group(1)
            break

    total_patterns = [
        r"\bGrand Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"\bNet Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"\bTotal[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"\bAmount[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
    ]
    for p in total_patterns:
        m = re.search(p, text, re.I)
        if m:
            total = m.group(1)
            break

    if not shop_name:
        for ln in lines:
            if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax|phone|mobile|email)\b", ln, re.I):
                shop_name = ln[:80]
                break

    return {
        "shop_name": shop_name,
        "bill_date": bill_date,
        "gst_number": gst_number,
        "items": heuristic_extract_items(text),
        "total": total,
        "raw_text": text,
    }

def normalize_result(data, fallback_text=""):
    if not isinstance(data, dict):
        data = {}
    raw_text = str(data.get("raw_text") or fallback_text or "").strip()
    if not data.get("items") or len(data["items"]) == 0:
        if raw_text:
            parsed = heuristic_parse_from_text(raw_text)
            data["items"] = parsed.get("items") or []
            if not data.get("shop_name"): data["shop_name"] = parsed.get("shop_name")
            if not data.get("bill_date"): data["bill_date"] = parsed.get("bill_date")
            if not data.get("gst_number"): data["gst_number"] = parsed.get("gst_number")
            if not data.get("total"): data["total"] = parsed.get("total")
    if not data.get("shop_name"):
        data["shop_name"] = "Unknown Shop"
    if not data.get("bill_date"):
        data["bill_date"] = datetime.now().strftime("%Y-%m-%d")
    if not data.get("gst_number"):
        data["gst_number"] = "N/A"
    if not data.get("total"):
        data["total"] = "0"
    data["raw_text"] = raw_text
    return data

def try_gemini(model, image):
    try:
        resp = model.generate_content(
            [build_schema_prompt(), image],
            generation_config={"temperature": 0, "response_mime_type": "application/json"},
        )
        data = parse_json_from_response(getattr(resp, "text", ""))
        st.session_state.gemini_available = True
        st.session_state.last_gemini_error_time = None
        return normalize_result(data), None
    except Exception as e:
        if is_gemini_quota_error(e):
            st.session_state.gemini_available = False
            st.session_state.last_gemini_error_time = datetime.now()
        return None, e

def try_perplexity(client, image):
    b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
    resp = client.chat.completions.create(
        model=secret_or_default("PERPLEXITY_MODEL", "sonar-pro"),
        messages=[
            {"role": "system", "content": build_schema_prompt()},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract invoice JSON from this image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            ]},
        ],
        temperature=0.0,
    )
    return normalize_result(parse_json_from_response(resp.choices[0].message.content))

def try_openai(client, image):
    b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
    resp = client.chat.completions.create(
        model=secret_or_default("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": build_schema_prompt()},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract invoice JSON from this image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            ]},
        ],
        response_format={"type": "json_object"},
    )
    return normalize_result(parse_json_from_response(resp.choices[0].message.content))

def analyze_with_auto_fallback(model_bundle, image, forced=None):
    image = preprocess_for_ocr(image)
    order = ["Gemini", "Google Vision OCR", "Perplexity", "OpenAI"]
    if forced in order:
        order = [forced] + [x for x in order if x != forced]

    for provider in order:
        try:
            if provider == "Gemini" and model_bundle.get("gemini") and can_try_gemini():
                data, _ = try_gemini(model_bundle["gemini"], image)
                if data: return data
            elif provider == "Google Vision OCR" and model_bundle.get("vision_client"):
                text = extract_vision_text(model_bundle["vision_client"], image)
                if text: return normalize_result(heuristic_parse_from_text(text), text)
            elif provider == "Perplexity" and model_bundle.get("perplexity"):
                return try_perplexity(model_bundle["perplexity"], image)
            elif provider == "OpenAI" and model_bundle.get("openai"):
                return try_openai(model_bundle["openai"], image)
        except Exception:
            continue

    return normalize_result(heuristic_parse_from_text(""), "")

def insert_bill(shop, date, gst, total, calc_total, status):
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO bills
            (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (shop, date, gst, float(total), float(calc_total), status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()

def sanitize_sheet_name(name, fallback="Sheet"):
    name = re.sub(r"[\[\]\*\?\/\\:]", "_", str(name)).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:31] or fallback)

def build_excel_export(results):
    buffer = BytesIO()
    wb = openpyxl.Workbook()
    
    ws1 = wb.active
    ws1.title = "Summary Dashboard"
    ws1.views.sheetView[0].showGridLines = True

    navy_dark = "1F4E78"
    navy_zebra = "F2F4F8"
    white = "FFFFFF"
    gray_border = "D9D9D9"

    font_title = Font(name="Calibri", size=16, bold=True, color="1F4E78")
    font_section = Font(name="Calibri", size=12, bold=True, color="1F4E78")
    font_header = Font(name="Calibri", size=11, bold=True, color=white)
    font_bold = Font(name="Calibri", size=11, bold=True)
    font_regular = Font(name="Calibri", size=11)

    fill_header = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
    fill_zebra = PatternFill(start_color=navy_zebra, end_color=navy_zebra, fill_type="solid")

    thin_side = Side(border_style="thin", color=gray_border)
    border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    border_total = Border(top=Side(border_style="thin", color="000000"), bottom=Side(border_style="double", color="000000"))

    ws1["A1"] = "AI OCR PROCESSOR - INVOICE BATCH SUMMARY"
    ws1["A1"].font = font_title
    ws1["A2"] = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws1["A2"].font = Font(name="Calibri", size=11, italic=True)

    ws1["A4"] = "1. Document-wise Statement Breakdown"
    ws1["A4"].font = font_section

    headers_bill = ["Sr No.", "Source File / Page", "Shop / Vendor Name", "Date", "Original Total", "Calculated Total", "Status"]
    for col_num, h in enumerate(headers_bill, 1):
        cell = ws1.cell(row=5, column=col_num, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws2 = wb.create_sheet(title="Detailed Transactions")
    ws2.views.sheetView[0].showGridLines = True
    headers_det = ["Source File", "Shop Name", "Date", "Item Name / Particulars", "Qty", "Rate", "Extracted Amount"]
    for col_num, h in enumerate(headers_det, 1):
        cell = ws2.cell(row=1, column=col_num, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")

    det_idx = 2
    row_idx = 6

    for idx, item in enumerate(results):
        d = item.get("data") or {}
        source = item.get("source", "Unknown")
        page = item.get("page", 1)
        shop = d.get("shop_name", "Unknown Shop")
        date_str = d.get("bill_date", "N/A")
        
        items = normalize_items(d.get("items"))
        calc_total = 0.0
        for it in items:
            amt = safe_float(it.get("amount")) or (safe_float(it.get("qty")) * safe_float(it.get("rate")))
            calc_total += amt
            
            ws2.cell(row=det_idx, column=1, value=source)
            ws2.cell(row=det_idx, column=2, value=shop)
            ws2.cell(row=det_idx, column=3, value=date_str)
            ws2.cell(row=det_idx, column=4, value=it.get("name", "Unknown"))
            ws2.cell(row=det_idx, column=5, value=safe_float(it.get("qty")))
            ws2.cell(row=det_idx, column=6, value=safe_float(it.get("rate")))
            ws2.cell(row=det_idx, column=7, value=amt).number_format = "₹#,##0.00"
            for c in range(1, 8):
                cell = ws2.cell(row=det_idx, column=c)
                cell.font = font_regular
                cell.border = border_all
                if det_idx % 2 == 1: cell.fill = fill_zebra
            det_idx += 1

        orig_total = safe_float(d.get("total")) or calc_total
        status = "Needs Review" if orig_total <= 0 else ("Verified Matched" if abs(calc_total - orig_total) < 1 else "Mismatch")

        ws1.cell(row=row_idx, column=1, value=idx + 1).alignment = Alignment(horizontal="center")
        ws1.cell(row=row_idx, column=2, value=f"{source} (P.{page})")
        ws1.cell(row=row_idx, column=3, value=shop)
        ws1.cell(row=row_idx, column=4, value=date_str).alignment = Alignment(horizontal="center")
        
        c_orig = ws1.cell(row=row_idx, column=5, value=orig_total)
        c_orig.number_format = "₹#,##0.00"
        
        c_calc = ws1.cell(row=row_idx, column=6, value=calc_total)
        c_calc.number_format = "₹#,##0.00"
        
        ws1.cell(row=row_idx, column=7, value=status).alignment = Alignment(horizontal="center")

        for c in range(1, 8):
            cell = ws1.cell(row=row_idx, column=c)
            cell.font = font_regular
            cell.border = border_all
            if row_idx % 2 == 1: cell.fill = fill_zebra
        row_idx += 1

    if row_idx > 6:
        ws1.cell(row=row_idx, column=3, value="Grand Total").font = font_bold
        ws1.cell(row=row_idx, column=5, value=f"=SUM(E6:E{row_idx-1})").font = font_bold
        ws1.cell(row=row_idx, column=5).number_format = "₹#,##0.00"
        ws1.cell(row=row_idx, column=5).border = border_total
        
        ws1.cell(row=row_idx, column=6, value=f"=SUM(F6:F{row_idx-1})").font = font_bold
        ws1.cell(row=row_idx, column=6).number_format = "₹#,##0.00"
        ws1.cell(row=row_idx, column=6).border = border_total

    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

def build_batch_summary(results):
    rows = []
    for item in results:
        d = item.get("data")
        if d:
            items = normalize_items(d.get("items"))
            calc_total = 0.0
            for it in items:
                calc_total += safe_float(it.get("amount")) or (safe_float(it.get("qty")) * safe_float(it.get("rate")))
                
            total = safe_float(d.get("total"))
            if total == 0.0 and calc_total > 0:
                total = calc_total
                
            shop = str(d.get("shop_name") or "Unknown Shop").strip()
            bill_date = str(d.get("bill_date") or datetime.now().strftime("%Y-%m-%d")).strip()
            status = "Needs Review" if total <= 0 else ("Matched" if abs(calc_total - total) < 1 else "Mismatch")
            
            try:
                insert_bill(shop, bill_date, d.get("gst_number"), total, calc_total, status)
            except Exception:
                pass

            rows.append({
                "page": item.get("page"),
                "source": item.get("source"),
                "shop_name": shop,
                "bill_date": bill_date,
                "gst_number": d.get("gst_number") or "N/A",
                "bill_total": total,
                "calculated_total": calc_total,
                "difference": abs(calc_total - total),
                "status": status
            })
        else:
            rows.append({
                "page": item.get("page"),
                "source": item.get("source"),
                "shop_name": "Unknown Shop",
                "bill_date": None,
                "gst_number": None,
                "bill_total": None,
                "calculated_total": None,
                "difference": None,
                "status": f"Error: {item.get('error')}"
            })
    return pd.DataFrame(rows)

def render_theme_toggle(location="main"):
    mode = st.radio("Theme", ["light", "dark"], horizontal=True, index=0 if st.session_state.get("theme_mode", "light") == "light" else 1, key=f"theme_radio_{location}")
    if mode != st.session_state.get("theme_mode", "light"):
        st.session_state["theme_mode"] = mode
        st.rerun()

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

def share_whatsapp(text): return "https://wa.me/?text=" + urllib.parse.quote(text)
def share_telegram(text): return "https://t.me/share/url?url=&text=" + urllib.parse.quote(text)
def share_email(text, subject="Bill Dashboard Report"): return "mailto:?subject=" + urllib.parse.quote(subject) + "&body=" + urllib.parse.quote(text)

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
        providers = ["Gemini", "Google Vision OCR", "Perplexity", "OpenAI"]
        st.session_state.selected_provider = st.selectbox("Select OCR Provider", providers, index=providers.index("Gemini"), key="provider_selectbox")

        uploaded_files = st.file_uploader(
            "Upload Bill Images or PDFs",
            type=["jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=True,
            key="bill_uploader",
        )

        col_a, col_b = st.columns(2)
        with col_a: process_now = st.button("Process All Files", use_container_width=True)
        with col_b: clear_state = st.button("Clear Uploaded / Processed Files", use_container_width=True)

        if clear_state:
            st.session_state.processed_files = set()
            st.session_state.current_results = []
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
                name_lower = uploaded_file.name.lower()

                if name_lower.endswith(".pdf"):
                    try:
                        pages = convert_pdf_to_images(file_bytes)
                        for i, img in enumerate(pages):
                            img = preprocess_for_ocr(img)
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
                st.session_state.current_results.extend(all_results)

        if st.session_state.current_results:
            df = build_batch_summary(st.session_state.current_results)
            render_metrics(df)
            
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

            st.subheader("📦 Extracted Bill Items Detail")
            for res in st.session_state.current_results:
                if res.get("data") and res["data"].get("items"):
                    st.markdown(f"**File: {res['source']} (Page {res['page']})**")
                    st.dataframe(pd.DataFrame(res["data"]["items"]), use_container_width=True)

            summary_text = make_share_text(df)
            s1, s2, s3 = st.columns(3)
            with s1: st.link_button("📱 Share on WhatsApp", share_whatsapp(summary_text), use_container_width=True)
            with s2: st.link_button("✈️ Share on Telegram", share_telegram(summary_text), use_container_width=True)
            with s3: st.link_button("📧 Share by Email", share_email(summary_text), use_container_width=True)

            excel_data = build_excel_export(st.session_state.current_results)
            st.download_button(
                "📥 Download Excel Report",
                data=excel_data,
                file_name="AI_Processed_Bills_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            if not uploaded_files:
                st.info("Upload images or PDFs, then click Process All Files.")

    with tabs[1]:
        st.subheader("Processing History")
        with sqlite3.connect(DB_PATH) as conn:
            history_df = pd.read_sql_query("SELECT * FROM bills ORDER BY timestamp DESC", conn)
        st.dataframe(history_df, use_container_width=True)

    with tabs[2]:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        render_theme_toggle("settings")
        st.markdown('</div>', unsafe_allow_html=True)

def main():
    setup_page()
    init_db()
    init_auth()
    init_runtime_state()
    apply_theme_css()
    apply_css()

    if not st.session_state.logged_in:
        do_login()
    else:
        render_upload_module()
        if st.sidebar.button("Logout"):
            terminate_session()

if __name__ == "__main__":
    main()
