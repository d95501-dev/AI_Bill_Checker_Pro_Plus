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

import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

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
    import boto3
except Exception:
    boto3 = None

try:
    import win32print
    WINDOWS_PRINTER_AVAILABLE = True
except Exception:
    WINDOWS_PRINTER_AVAILABLE = False

try:
    from pdf2image import convert_from_bytes
except Exception:
    convert_from_bytes = None

try:
    from google.cloud import vision
except Exception:
    vision = None

try:
    from google.cloud import documentai
except Exception:
    documentai = None

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
        .stButton>button {
            background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            padding: 12px 24px !important;
            border-radius: 12px !important;
            border: none !important;
        }
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
            {"role": "user", "content": [
                {"type": "text", "text": "Extract invoice JSON from this image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]},
        ],
        response_format={"type": "json_object"},
    )
    return parse_json_from_response(resp.choices[0].message.content)


def analyze_google_vision(client, image):
    if client is None:
        raise RuntimeError("Google Vision not configured")
    b = image_to_bytes(image)
    img = vision.Image(content=b)
    resp = client.document_text_detection(image=img)
    text = getattr(resp, "full_text_annotation", None)
    extracted = getattr(text, "text", "") if text else ""
    return heuristic_parse_from_text(extracted)


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

    return {"shop_name": shop_name, "bill_date": bill_date, "gst_number": gst_number, "items": items, "total": total}


def analyze_with_auto_fallback(model_bundle, image):
    provider = st.session_state.get("selected_provider", "Google Vision OCR")
    order = [provider, "Google Vision OCR", "Gemini", "OpenAI"]
    seen = set()
    last_err = None

    for p in order:
        if p in seen:
            continue
        seen.add(p)
        try:
            if p == "Google Vision OCR" and model_bundle.get("vision_client") and st.session_state.get("vision_enabled", True):
                return analyze_google_vision(model_bundle["vision_client"], image)

            if p == "Gemini" and model_bundle.get("gemini") and can_try_gemini():
                result = analyze_gemini(model_bundle["gemini"], image)
                st.session_state.gemini_available = True
                st.session_state.last_gemini_error_time = None
                st.session_state.gemini_retry_count = 0
                return result

            if p == "OpenAI" and model_bundle.get("openai"):
                return analyze_openai(model_bundle["openai"], image)

        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if p == "Gemini" and ("429" in msg or "quota" in msg or "rate limit" in msg):
                st.session_state.gemini_available = False
                st.session_state.last_gemini_error_time = datetime.now()
                st.session_state.gemini_retry_count += 1
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
