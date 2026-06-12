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
                UNIQUE(shop_name, bill_date, total)
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
            box-shadow:
                0 18px 40px rgba(15, 23, 42, 0.22),
                inset 0 1px 0 rgba(255,255,255,0.12);
            transform: translateY(0);
            transition: all 0.25s ease;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            flex-wrap: wrap;
        }

        .deep-csc-header:hover {
            transform: translateY(-2px);
        }

        .branding-text h1 {
            margin: 0;
            font-size: 34px !important;
            font-weight: 800;
            letter-spacing: -0.6px;
            background: linear-gradient(to right, #38bdf8, #c084fc, #f43f5e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 10px 30px rgba(0,0,0,0.18);
        }

        .branding-text p {
            margin: 6px 0 0 0;
            color: #cbd5e1;
            font-size: 14px;
        }

        .branding-badge {
            background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%);
            color: white !important;
            padding: 9px 16px;
            border-radius: 999px;
            font-size: 12px !important;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            box-shadow: 0 10px 25px rgba(139, 92, 246, 0.35);
        }

        .csc-meta-badge {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            color: #e2e8f0 !important;
            padding: 12px 16px;
            border-radius: 16px;
            font-size: 13px !important;
            line-height: 1.7;
            backdrop-filter: blur(10px);
            box-shadow: 0 14px 35px rgba(15, 23, 42, 0.10);
        }

        .metric-card {
            background: rgba(255,255,255,0.82);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 22px;
            padding: 18px 20px;
            box-shadow:
                0 14px 35px rgba(15, 23, 42, 0.10),
                inset 0 1px 0 rgba(255,255,255,0.7);
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .metric-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.14);
        }

        .metric-label {
            color: #64748b;
            font-size: 13px;
            margin-bottom: 8px;
        }

        .metric-value {
            font-size: 28px;
            font-weight: 800;
            color: #0f172a;
            line-height: 1.1;
        }

        .metric-sub {
            margin-top: 6px;
            color: #64748b;
            font-size: 13px;
        }

        .section-card {
            background: rgba(255,255,255,0.78);
            border: 1px solid rgba(148,163,184,0.16);
            border-radius: 22px;
            padding: 18px;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.05);
            backdrop-filter: blur(8px);
        }

        .stButton > button {
            background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            border: none !important;
            border-radius: 14px !important;
            padding: 12px 22px !important;
            box-shadow: 0 12px 26px rgba(37,99,235,0.28);
            transition: all 0.2s ease;
        }

        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 16px 30px rgba(37,99,235,0.36);
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            background: rgba(255,255,255,0.55);
            padding: 8px;
            border-radius: 18px;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 14px;
            padding: 10px 18px;
            font-weight: 700;
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #0f172a 0%, #4338ca 100%) !important;
            color: white !important;
        }

        div[data-testid="stDataFrame"] {
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 14px 35px rgba(15, 23, 42, 0.08);
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        }

        section[data-testid="stSidebar"] * {
            color: #f8fafc !important;
        }

        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2rem;
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
                "name": it.get("name") or "",
                "qty": it.get("qty") or "",
                "rate": it.get("rate") or "",
                "amount": it.get("amount") or ""
            })
    return cleaned

def parse_json_from_response(response_text):
    raw = (response_text or "").strip().replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
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
    return (not last_error) or ((datetime.now() - last_error).total_seconds() >= st.session_state.get("gemini_cooldown_seconds", 900))

def is_gemini_quota_error(err):
    msg = str(err).lower()
    return ("429" in msg) or ("quota" in msg) or ("resource_exhausted" in msg) or ("rate limit" in msg)

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

def preprocess_for_ocr(image):
    try:
        import cv2
        import numpy as np
        img = np.array(image)
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
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        doc.close()
        return images
    if pdfium is not None:
        pdf = pdfium.PdfDocument(file_bytes)
        images = []
        for i in range(len(pdf)):
            images.append(pdf[i].render(scale=2).to_pil().convert("RGB"))
        return images
    if convert_from_bytes is not None:
        return convert_from_bytes(file_bytes, dpi=200)
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
        r"\bBill Amount[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
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
    if raw_text:
        parsed = heuristic_parse_from_text(raw_text)
        for k, v in parsed.items():
            if not data.get(k):
                data[k] = v
    if not data.get("shop_name") and raw_text:
        lines = [x.strip() for x in raw_text.splitlines() if x.strip()]
        for ln in lines[:15]:
            if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax|phone|mobile|email)\b", ln, re.I):
                data["shop_name"] = ln[:80]
                break
    if not data.get("bill_date"):
        data["bill_date"] = datetime.now().strftime("%Y-%m-%d")
    if not data.get("gst_number"):
        data["gst_number"] = "N/A"
    if not data.get("items"):
        data["items"] = []
    if not data.get("total"):
        total_from_text = None
        for p in [
            r"\bGrand Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
            r"\bNet Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
            r"\bTotal[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        ]:
            m = re.search(p, raw_text, re.I)
            if m:
                total_from_text = m.group(1)
                break
        data["total"] = total_from_text or "0"
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
                if data:
                    return data
            elif provider == "Google Vision OCR" and model_bundle.get("vision_client"):
                text = extract_vision_text(model_bundle["vision_client"], image)
                if text:
                    return normalize_result(heuristic_parse_from_text(text), text)
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
            (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()

def sanitize_sheet_name(name, fallback="Sheet"):
    name = re.sub(r"[\[\]\*\?\/\\:]", "_", str(name)).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:31] or fallback)

def build_excel_export(results):
    buffer = BytesIO()
    wb = openpyxl.Workbook()
    
    # ----------------------------------------------------
    # Sheet 1: Summary Dashboard
    # ----------------------------------------------------
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

    # मुख्य टाइटल को डायनेमिक बनाना (पहले अपलोड किए गए बिल से दुकान का नाम उठाना)
    main_shop_name = "AI PROCESSED BILLS"
    if results and results[0].get("data") and results[0]["data"].get("shop_name"):
        main_shop_name = results[0]["data"]["shop_name"].upper()

    ws1["A1"] = f"{main_shop_name} - INVOICE SUMMARY & AUDIT"
    ws1["A1"].font = font_title
    ws1["A2"] = f"Generated via Deep CSC AI | Date: {datetime.now().strftime('%d/%m/%Y')}"
    ws1["A2"].font = Font(name="Calibri", size=11, italic=True)

    ws1["A4"] = "1. Statement / Bill-wise Breakdown"
    ws1["A4"].font = font_section

    headers_bill = ["Bill No / S.No", "Shop Name", "Bill Date", "Original Invoice Total", "Calculated Total", "Status / Audit"]
    for col_num, h in enumerate(headers_bill, 1):
        cell = ws1.cell(row=5, column=col_num, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # डायनेमिक बिल ब्रेकडाउन डेटा तैयार करना
    current_row = 6
    for idx, item in enumerate(results, 1):
        d = item.get("data")
        if not d:
            continue
        
        shop = d.get("shop_name") or "Unknown Shop"
        b_date = d.get("bill_date") or "N/A"
        orig_total = safe_float(d.get("total", 0))
        
        # आइटमों की कुल राशि कैलकुलेट करना
        items = normalize_items(d.get("items"))
        calc_total = sum(safe_float(it.get("amount", 0)) for it in items)
        
        ws1.cell(row=current_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws1.cell(row=current_row, column=2, value=shop).alignment = Alignment(horizontal="left")
        ws1.cell(row=current_row, column=3, value=b_date).alignment = Alignment(horizontal="center")
        
        c_orig = ws1.cell(row=current_row, column=4, value=orig_total)
        c_orig.number_format = "₹#,##0.00"
        c_orig.alignment = Alignment(horizontal="right")
        
        # एक्सेल फॉर्मूला लगाना ताकि शीट 2 से लाइव सम कर सके
        c_calc = ws1.cell(row=current_row, column=5, value=f"=SUMIF('Detailed Transactions'!A:A, A{current_row}, 'Detailed Transactions'!G:G)")
        c_calc.number_format = "₹#,##0.00"
        c_calc.alignment = Alignment(horizontal="right")
        
        c_status = ws1.cell(row=current_row, column=6, value=f'=IF(ABS(D{current_row}-E{current_row})<1, "Verified Matched", "Mismatch")')
        c_status.alignment = Alignment(horizontal="center")
        
        for c in range(1, 7):
            cell = ws1.cell(row=current_row, column=c)
            cell.font = font_regular
            cell.border = border_all
            if current_row % 2 == 1:
                cell.fill = fill_zebra
        current_row += 1

    # ग्रैंड टोटल रो
    ws1.cell(row=current_row, column=1, value="Grand Total").font = font_bold
    ws1.cell(row=current_row, column=4, value=f"=SUM(D6:D{current_row-1})").font = font_bold
    ws1.cell(row=current_row, column=4).number_format = "₹#,##0.00"
    ws1.cell(row=current_row, column=4).border = border_total
    
    ws1.cell(row=current_row, column=5, value=f"=SUM(E6:E{current_row-1})").font = font_bold
    ws1.cell(row=current_row, column=5).number_format = "₹#,##0.00"
    ws1.cell(row=current_row, column=5).border = border_total
    
    # ----------------------------------------------------
    # Sheet 2: Detailed Transactions
    # ----------------------------------------------------
    ws2 = wb.create_sheet(title="Detailed Transactions")
    ws2.views.sheetView[0].showGridLines = True
    
    headers_det = ["Bill Index", "Date", "Shop Name", "Item Description", "Qty", "Rate", "Amount (₹)"]
    for col_num, h in enumerate(headers_det, 1):
        cell = ws2.cell(row=1, column=col_num, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")

    det_row = 2
    for idx, item in enumerate(results, 1):
        d = item.get("data")
        if not d:
            continue
        
        shop = d.get("shop_name") or "Unknown Shop"
        b_date = d.get("bill_date") or "N/A"
        items = normalize_items(d.get("items"))
        
        # डेटाबेस में हिस्ट्री एंट्री के लिए सेव करना
        try:
            orig_t = safe_float(d.get("total", 0))
            calc_t = sum(safe_float(it.get("amount", 0)) for it in items)
            stat_str = "Matched" if abs(calc_t - orig_t) < 1 else "Mismatch"
            insert_bill(shop, b_date, d.get("gst_number") or "N/A", orig_t, calc_t, stat_str)
        except Exception:
            pass

        if not items:
            # अगर कोई आइटम नहीं मिला तो ब्लैंक रो की जगह मूल कुल राशि डाल दें
            ws2.cell(row=det_row, column=1, value=idx).alignment = Alignment(horizontal="center")
            ws2.cell(row=det_row, column=2, value=b_date).alignment = Alignment(horizontal="center")
            ws2.cell(row=det_row, column=3, value=shop).alignment = Alignment(horizontal="left")
            ws2.cell(row=det_row, column=4, value="Total Bill (Items Extraction Missing)").alignment = Alignment(horizontal="left")
            ws2.cell(row=det_row, column=5, value=1).alignment = Alignment(horizontal="right")
            ws2.cell(row=det_row, column=6, value=safe_float(d.get("total", 0))).alignment = Alignment(horizontal="right")
            ws2.cell(row=det_row, column=7, value=f"=E{det_row}*F{det_row}").alignment = Alignment(horizontal="right")
            
            for c in range(1, 8):
                cell = ws2.cell(row=det_row, column=c)
                cell.font = font_regular
                cell.border = border_all
            det_row += 1
        else:
            for it in items:
                ws2.cell(row=det_row, column=1, value=idx).alignment = Alignment(horizontal="center")
                ws2.cell(row=det_row, column=2, value=b_date).alignment = Alignment(horizontal="center")
                ws2.cell(row=det_row, column=3, value=shop).alignment = Alignment(horizontal="left")
                ws2.cell(row=det_row, column=4, value=it.get("name") or "Item").alignment = Alignment(horizontal="left")
                
                q_val = safe_float(it.get("qty", 1))
                r_val = safe_float(it.get("rate", 0))
                
                q_cell = ws2.cell(row=det_row, column=5, value=q_val)
                q_cell.number_format = "#,##0.00"
                q_cell.alignment = Alignment(horizontal="right")
                
                r_cell = ws2.cell(row=det_row, column=6, value=r_val)
                r_cell.number_format = "₹#,##0.00"
                r_cell.alignment = Alignment(horizontal="right")
                
                a_cell = ws2.cell(row=det_row, column=7, value=f"=E{det_row}*F{det_row}")
                a_cell.number_format = "₹#,##0.00"
                a_cell.alignment = Alignment(horizontal="right")
                
                for c in range(1, 8):
                    cell = ws2.cell(row=det_
