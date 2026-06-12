import base64
import json
import logging
import os
import random
import re
import sqlite3
import time
import urllib.parse
import warnings
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bill_processor")

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

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
PROVIDERS = ["Gemini", "Google Vision OCR", "Perplexity", "OpenAI"]


@dataclass
class OCRResult:
    shop_name: str
    bill_date: str
    gst_number: str
    items: list
    total: float
    raw_text: str = ""


def secret_or_default(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return default


def setup_page():
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide", initial_sidebar_state="expanded")


def init_state():
    defaults = {
        "logged_in": False,
        "selected_provider": "Gemini",
        "theme_mode": "light",
        "processed_files": set(),
        "gemini_available": True,
        "last_gemini_error_time": None,
        "gemini_cooldown_seconds": 900,
        "ocr_failures": 0,
        "file_statuses": [],
        "error_log": [],
        "provider_stats": {
            "Gemini": {"ok": 0, "fail": 0},
            "Google Vision OCR": {"ok": 0, "fail": 0},
            "Perplexity": {"ok": 0, "fail": 0},
            "OpenAI": {"ok": 0, "fail": 0},
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


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


def login_screen():
    st.markdown(
        """
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
        .login-sub { margin-top: 8px; color: #64748b; font-size: 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
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


def logout():
    st.session_state.logged_in = False
    for k in list(st.session_state.keys()):
        if k != "logged_in":
            del st.session_state[k]
    st.rerun()


def apply_theme_css():
    dark = st.session_state.get("theme_mode", "light") == "dark"
    bg = "#0b1220" if dark else "#f8fafc"
    sidebar = "#0f172a"
    text = "#e5e7eb" if dark else "#0f172a"
    sidebar_text = "#f8fafc"
    st.markdown(
        f"""<style>.stApp {{ background: {bg}; color: {text}; }} section[data-testid="stSidebar"] {{ background: {sidebar}; }} section[data-testid="stSidebar"] * {{ color: {sidebar_text} !important; }}</style>""",
        unsafe_allow_html=True,
    )


def apply_css():
    st.markdown(
        """
        <style>
        .stApp { background: radial-gradient(circle at top left, #ffffff 0%, #eef2ff 45%, #e2e8f0 100%); }
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
        """,
        unsafe_allow_html=True,
    )


def metric_card(label, value, sub=""):
    st.markdown(f"""<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-sub">{sub}</div></div>""", unsafe_allow_html=True)


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


def image_to_bytes(image):
    buf = BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=96, optimize=True)
    return buf.getvalue()


def preprocess_for_ocr(image):
    try:
        import cv2
        import numpy as np
        img = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, None, 18, 7, 21)
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
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        doc.close()
        return images
    if pdfium is not None:
        pdf = pdfium.PdfDocument(file_bytes)
        return [pdf[i].render(scale=2.5).to_pil().convert("RGB") for i in range(len(pdf))]
    if convert_from_bytes is not None:
        return convert_from_bytes(file_bytes, dpi=300)
    raise RuntimeError("No PDF rendering library available.")


def clean_text(text):
    text = text or ""
    text = text.replace("\x0c", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_float(value):
    if value is None:
        return 0.0
    s = str(value).strip()
    s = s.replace("₹", "").replace("Rs.", "").replace("Rs", "").replace(",", "").replace(" ", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s not in ("", ".", "-", "-.") else 0.0
    except Exception:
        return 0.0


def normalize_items(items):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for it in items:
        if not isinstance(it, dict):
            continue
        name = re.sub(r"\s+", " ", str(it.get("name") or "").strip())
        qty = str(it.get("qty") or "").strip()
        rate = str(it.get("rate") or "").strip()
        amount = str(it.get("amount") or "").strip()
        if not name:
            continue
        cleaned.append({"name": name[:120], "qty": qty, "rate": rate, "amount": amount})
    return cleaned[:100]


def parse_json_from_response(response_text):
    raw = (response_text or "").strip().replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    return json.loads(raw)


def extract_shop_name(text):
    text = clean_text(text)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    ignore = re.compile(r"\b(invoice|bill|gst|date|total|amount|tax|phone|mobile|email|mrp|rate|qty|cash|upi)\b", re.I)
    for ln in lines[:20]:
        if len(ln) >= 4 and not ignore.search(ln):
            if len(re.findall(r"\d", ln)) <= 3:
                return re.sub(r"\s+", " ", ln)[:100]
    return "Unknown Shop"


def extract_gst_number(text):
    text = text or ""
    patterns = [r"\bGSTIN[:\s-]*([0-9A-Z]{15})\b", r"\b([0-9A-Z]{2}[0-9A-Z]{13})\b"]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            val = m.group(1).upper()
            if len(val) == 15:
                return val
    return "N/A"


def normalize_date(value):
    if not value:
        return None
    s = str(value).strip().replace(".", "/").replace("-", "/")
    fmts = ["%Y/%m/%d", "%d/%m/%Y", "%d/%m/%y", "%d %B %Y", "%d %b %Y", "%d %m %Y"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def extract_bill_date(text):
    text = clean_text(text)
    patterns = [
        r"\bDate[:\s-]*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})\b",
        r"\bDate[:\s-]*([0-9]{2}[-/][0-9]{2}[-/][0-9]{2,4})\b",
        r"\b([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})\b",
        r"\b([0-9]{2}[-/][0-9]{2}[-/][0-9]{2,4})\b",
        r"\b([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            d = normalize_date(m.group(1))
            if d:
                return d
    return datetime.now().strftime("%Y-%m-%d")


def extract_total(text):
    text = clean_text(text)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    patterns = [
        r"(?i)\bgrand\s*total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"(?i)\bnet\s*total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"(?i)\bbill\s*amount[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"(?i)\bamount[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"(?i)\btotal[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
    ]
    candidates = []
    for p in patterns:
        for m in re.finditer(p, text):
            v = safe_float(m.group(1))
            if v > 0:
                candidates.append(v)
    for ln in lines[-10:]:
        nums = re.findall(r"\d+(?:,\d{3})*(?:\.\d{1,2})?", ln)
        if nums:
            last = safe_float(nums[-1])
            if last > 0:
                candidates.append(last)
    return max(candidates) if candidates else 0.0


def heuristic_extract_items(text):
    text = clean_text(text)
    items = []
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    stop_words = re.compile(r"\b(invoice|bill|gst|date|total|amount|tax|phone|mobile|email|upi|cash|change|mrp)\b", re.I)
    for ln in lines:
        if stop_words.search(ln):
            continue
        nums = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", ln)
        if len(nums) >= 2:
            amount = safe_float(nums[-1])
            rate = safe_float(nums[-2])
            qty = safe_float(nums[-3]) if len(nums) >= 3 else 0.0
            name = re.sub(r"\d+(?:,\d{3})*(?:\.\d+)?", " ", ln)
            name = re.sub(r"[\\|\:\-]+", " ", name)
            name = re.sub(r"\s+", " ", name).strip()
            if len(name) >= 2 and amount > 0:
                items.append({"name": name[:120], "qty": str(qty) if qty > 0 else "", "rate": str(rate) if rate > 0 else "", "amount": str(amount)})
    return items[:100]


def heuristic_parse_from_text(text):
    text = clean_text(text)
    return OCRResult(extract_shop_name(text), extract_bill_date(text), extract_gst_number(text), heuristic_extract_items(text), extract_total(text), text)


def normalize_result(data, fallback_text=""):
    if not isinstance(data, dict):
        data = {}
    raw_text = clean_text(str(data.get("raw_text") or fallback_text or ""))
    heur = heuristic_parse_from_text(raw_text)
    shop = data.get("shop_name") or heur.shop_name
    bill_date = data.get("bill_date") or heur.bill_date
    gst_number = data.get("gst_number") or heur.gst_number
    items = data.get("items") or heur.items
    total = data.get("total") if data.get("total") not in (None, "", "N/A") else heur.total
    if not normalize_date(bill_date):
        bill_date = heur.bill_date
    return {"shop_name": str(shop).strip() or "Unknown Shop", "bill_date": normalize_date(bill_date) or heur.bill_date, "gst_number": str(gst_number).strip() or "N/A", "items": normalize_items(items), "total": safe_float(total), "raw_text": raw_text}


def build_schema_prompt():
    return """
You are an expert document extraction specialist specializing in handwritten Indian market bills.
Return ONLY valid JSON with schema:
{
  "shop_name": "string",
  "bill_date": "YYYY-MM-DD or string",
  "gst_number": "string or null",
  "items": [{"name":"string","qty":"string","rate":"string","amount":"string"}],
  "total": "string"
}
Extract ALL visible data from the bill. No markdown, no explanation.
"""


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


def can_try_gemini():
    if st.session_state.get("gemini_available", True):
        return True
    last_error = st.session_state.get("last_gemini_error_time")
    cooldown = st.session_state.get("gemini_cooldown_seconds", 900)
    return (not last_error) or ((datetime.now() - last_error).total_seconds() >= cooldown)


def is_gemini_quota_error(err):
    msg = str(err).lower()
    return ("429" in msg) or ("quota" in msg) or ("resource_exhausted" in msg) or ("rate limit" in msg)


def retry_call(fn, retries=3, base_delay=1.0, retry_on_result_none=True):
    last_err = None
    for attempt in range(retries):
        try:
            result = fn()
            if not retry_on_result_none or result is not None:
                return result
        except Exception as e:
            last_err = e
        time.sleep(min(10.0, base_delay * (2 ** attempt)) + random.uniform(0, 0.5))
    if last_err:
        raise last_err
    return None


def add_error(provider, file_name, message):
    st.session_state.error_log.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "provider": provider, "file_name": file_name, "message": str(message)})
    st.session_state.error_log = st.session_state.error_log[-100:]


def record_provider_result(provider, success=True):
    if provider not in st.session_state.provider_stats:
        st.session_state.provider_stats[provider] = {"ok": 0, "fail": 0}
    if success:
        st.session_state.provider_stats[provider]["ok"] += 1
    else:
        st.session_state.provider_stats[provider]["fail"] += 1


def get_status_badge_text(status):
    if status == "Matched":
        return ":green-badge[Matched]"
    if status == "Mismatch":
        return ":orange-badge[Mismatch]"
    if status == "Needs Review":
        return ":red-badge[Needs Review]"
    if status == "Processing":
        return ":blue-badge[Processing]"
    if status == "Skipped":
        return ":gray-badge[Skipped]"
    return ":gray-badge[Unknown]"


def render_status_badges(df=None):
    if df is None or df.empty:
        st.markdown(":gray-badge[No files processed yet]")
        return
    matched = int((df["status"] == "Matched").sum())
    mismatch = int((df["status"] == "Mismatch").sum())
    review = int((df["status"] == "Needs Review").sum())
    total = len(df)
    st.markdown(f":blue-badge[Total: {total}] :green-badge[Matched: {matched}] :orange-badge[Mismatch: {mismatch}] :red-badge[Review: {review}]")


def render_error_panel():
    with st.expander("⚠️ Structured Error Panel", expanded=False):
        if not st.session_state.error_log:
            st.success("No errors captured yet.")
            return
        err_df = pd.DataFrame(st.session_state.error_log)
        st.dataframe(err_df, use_container_width=True)
        st.markdown("### Provider Health")
        health_rows = []
        for provider, stats in st.session_state.provider_stats.items():
            health_rows.append({"provider": provider, "ok": stats["ok"], "fail": stats["fail"], "health": "Healthy" if stats["fail"] == 0 else "Degraded"})
        st.dataframe(pd.DataFrame(health_rows), use_container_width=True)
        st.download_button("⬇️ Download Error Log", data=err_df.to_csv(index=False).encode("utf-8"), file_name="error_log.csv", mime="text/csv", use_container_width=True)


def try_gemini(model, image):
    def _call():
        resp = model.generate_content([build_schema_prompt(), image], generation_config={"temperature": 0, "response_mime_type": "application/json"})
        return normalize_result(parse_json_from_response(getattr(resp, "text", "")))
    try:
        data = retry_call(_call, retries=3, base_delay=1.0)
        st.session_state.gemini_available = True
        st.session_state.last_gemini_error_time = None
        return data, None
    except Exception as e:
        if is_gemini_quota_error(e):
            st.session_state.gemini_available = False
            st.session_state.last_gemini_error_time = datetime.now()
        return None, e


def try_perplexity(client, image):
    b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
    def _call():
        resp = client.chat.completions.create(
            model=secret_or_default("PERPLEXITY_MODEL", "sonar-pro"),
            messages=[{"role": "system", "content": build_schema_prompt()}, {"role": "user", "content": [{"type": "text", "text": "Extract invoice JSON from this image."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}]}],
            temperature=0.0,
        )
        return normalize_result(parse_json_from_response(resp.choices[0].message.content))
    return retry_call(_call, retries=3, base_delay=1.0)


def try_openai(client, image):
    b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
    def _call():
        resp = client.chat.completions.create(
            model=secret_or_default("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": build_schema_prompt()}, {"role": "user", "content": [{"type": "text", "text": "Extract invoice JSON from this image."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}]}],
            response_format={"type": "json_object"},
        )
        return normalize_result(parse_json_from_response(resp.choices[0].message.content))
    return retry_call(_call, retries=3, base_delay=1.0)


def extract_vision_text(vision_client, image):
    def _call():
        img = vision.Image(content=image_to_bytes(image))
        resp = vision_client.document_text_detection(image=img)
        text = ""
        if getattr(resp, "full_text_annotation", None):
            text = getattr(resp.full_text_annotation, "text", "") or ""
        if not text.strip() and getattr(resp, "text_annotations", None):
            anns = resp.text_annotations
            if anns and getattr(anns[0], "description", ""):
                text = anns[0].description.strip()
        return clean_text(text)
    return retry_call(_call, retries=2, base_delay=0.5) or ""


def analyze_with_auto_fallback(model_bundle, image, forced=None, file_name="unknown"):
    image = preprocess_for_ocr(image)
    order = PROVIDERS[:]
    if forced in order:
        order = [forced] + [x for x in order if x != forced]
    for provider in order:
        try:
            if provider == "Gemini" and model_bundle.get("gemini") and can_try_gemini():
                data, _ = try_gemini(model_bundle["gemini"], image)
                if data:
                    record_provider_result(provider, True)
                    return data
            elif provider == "Google Vision OCR" and model_bundle.get("vision_client"):
                text = extract_vision_text(model_bundle["vision_client"], image)
                if text:
                    record_provider_result(provider, True)
                    return normalize_result({}, text)
            elif provider == "Perplexity" and model_bundle.get("perplexity"):
                data = try_perplexity(model_bundle["perplexity"], image)
                if data:
                    record_provider_result(provider, True)
                    return data
            elif provider == "OpenAI" and model_bundle.get("openai"):
                data = try_openai(model_bundle["openai"], image)
                if data:
                    record_provider_result(provider, True)
                    return data
        except Exception as e:
            record_provider_result(provider, False)
            add_error(provider, file_name, e)
            logger.warning("Provider %s failed on %s: %s", provider, file_name, e)
            continue
    st.session_state.ocr_failures += 1
    add_error("ALL_PROVIDERS", file_name, "All OCR providers failed")
    return normalize_result({}, "")


def insert_bill(shop, date, gst, total, calc_total, status):
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO bills (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()


def get_history_df():
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM bills ORDER BY timestamp DESC", conn)


def normalize_bill_row(row, fallback_index=1):
    d = row.get("data") or {}
    items = normalize_items(d.get("items"))
    tmp_df = pd.DataFrame(items)
    calc_total = float(pd.to_numeric(tmp_df["amount"], errors="coerce").fillna(0).sum()) if not tmp_df.empty else 0.0
    total = safe_float(d.get("total", 0))
    shop = str(d.get("shop_name") or "").strip() or "Unknown Shop"
    bill_date = str(d.get("bill_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    gst_number = d.get("gst_number") or "N/A"
    status = "Needs Review" if total <= 0 else ("Matched" if abs(calc_total - total) < 1 else "Mismatch")
    return {"page": row.get("page", fallback_index), "source": row.get("source", ""), "shop_name": shop, "bill_date": bill_date, "gst_number": gst_number, "bill_total": total, "calculated_total": calc_total, "difference": abs(calc_total - total), "status": status, "items": items}


def build_batch_summary(results):
    rows = []
    for idx, item in enumerate(results, 1):
        row = normalize_bill_row(item, idx)
        rows.append({"page": row["page"], "source": row["source"], "shop_name": row["shop_name"], "bill_date": row["bill_date"], "gst_number": row["gst_number"], "bill_total": row["bill_total"], "calculated_total": row["calculated_total"], "difference": row["difference"], "status": row["status"]})
        insert_bill(row["shop_name"], row["bill_date"], row["gst_number"], row["bill_total"], row["calculated_total"], row["status"])
    return pd.DataFrame(rows)


def make_share_text(df=None):
    total = len(df) if df is not None and not df.empty else 0
    matched = int((df["status"] == "Matched").sum()) if total else 0
    mismatch = int((df["status"] == "Mismatch").sum()) if total else 0
    review = int((df["status"] == "Needs Review").sum()) if total else 0
    return f"{APP_TITLE}\nFiles Processed: {total}\nMatched: {matched}\nMismatch: {mismatch}\nNeeds Review: {review}"


def share_whatsapp(text):
    return "https://wa.me/?text=" + urllib.parse.quote(text)


def share_telegram(text):
    return "https://t.me/share/url?url=&text=" + urllib.parse.quote(text)


def share_email(text, subject="Bill Dashboard Report"):
    return "mailto:?subject=" + urllib.parse.quote(subject) + "&body=" + urllib.parse.quote(text)


def render_theme_toggle(location="main"):
    mode = st.radio("Theme", ["light", "dark"], horizontal=True, index=0 if st.session_state.get("theme_mode", "light") == "light" else 1, key=f"theme_radio_{location}")
    if mode != st.session_state.get("theme_mode", "light"):
        st.session_state["theme_mode"] = mode
        st.rerun()


def _auto_widths(ws, min_width=12, max_width=30):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, min_width), max_width)


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

    normalized = [normalize_bill_row(r, i + 1) for i, r in enumerate(results)]
    vendors = sorted({row["shop_name"] for row in normalized if row.get("shop_name")})

    ws1["A1"] = "MULTI-BILL INVOICE SUMMARY & AUDIT"
    ws1["A1"].font = font_title
    ws1["A2"] = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws1["A2"].font = Font(name="Calibri", size=11, italic=True)
    ws1["A3"] = f"Vendors detected: {len(vendors)}"
    ws1["A3"].font = Font(name="Calibri", size=11, italic=True)

    if vendors:
        preview = " | ".join(vendors[:5])
        if len(vendors) > 5:
            preview += " ..."
        ws1["A4"] = preview
        ws1["A4"].font = Font(name="Calibri", size=10, italic=True)

    ws1["A6"] = "1. Bill-wise Breakdown"
    ws1["A6"].font = font_section

    headers_bill = ["Bill No.", "Source File", "Shop Name", "Bill Date", "Original Total", "Calculated Total", "Difference", "Status"]
    for col_num, h in enumerate(headers_bill, 1):
        c = ws1.cell(row=7, column=col_num, value=h)
        c.font = font_header
        c.fill = fill_header
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_all

    for idx, row in enumerate(normalized, 8):
        values = [
            idx - 7,
            row["source"],
            row["shop_name"],
            row["bill_date"],
            row["bill_total"],
            row["calculated_total"],
            row["difference"],
            row["status"],
        ]
        for cidx, val in enumerate(values, 1):
            cell = ws1.cell(row=idx, column=cidx, value=val)
            cell.font = font_regular
            cell.border = border_all
            if idx % 2 == 0:
                cell.fill = fill_zebra
        ws1.cell(row=idx, column=5).number_format = "₹#,##0.00"
        ws1.cell(row=idx, column=6).number_format = "₹#,##0.00"
        ws1.cell(row=idx, column=7).number_format = "₹#,##0.00"

    end_row = 7 + len(normalized)
    ws1.cell(row=end_row + 1, column=1, value="Grand Total").font = font_bold
    ws1.cell(row=end_row + 1, column=5, value=f"=SUM(E8:E{end_row})").font = font_bold
    ws1.cell(row=end_row + 1, column=5).number_format = "₹#,##0.00"
    ws1.cell(row=end_row + 1, column=6, value=f"=SUM(F8:F{end_row})").font = font_bold
    ws1.cell(row=end_row + 1, column=6).number_format = "₹#,##0.00"

    product_section_row = end_row + 4
    ws1.cell(row=product_section_row, column=1, value="2. Product Consumption Summary").font = font_section

    headers_prod = ["Product Name", "Total Qty", "Avg Rate", "Total Amount"]
    for col_num, h in enumerate(headers_prod, 1):
        c = ws1.cell(row=product_section_row + 1, column=col_num, value=h)
        c.font = font_header
        c.fill = fill_header
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_all

    item_aggregate = {}
    for row in normalized:
        for item in row["items"]:
            name = str(item.get("name") or "").strip() or "Unknown"
            qty = safe_float(item.get("qty", 0))
            rate = safe_float(item.get("rate", 0))
            amount = safe_float(item.get("amount", 0))

            if name not in item_aggregate:
                item_aggregate[name] = {"qty": 0.0, "rate_sum": 0.0, "rate_count": 0, "amount": 0.0}

            item_aggregate[name]["qty"] += qty
            if rate > 0:
                item_aggregate[name]["rate_sum"] += rate
                item_aggregate[name]["rate_count"] += 1
            item_aggregate[name]["amount"] += amount if amount > 0 else qty * rate

    prod_start = product_section_row + 2
    last_prod_row = prod_start - 1

    for idx, (name, data) in enumerate(sorted(item_aggregate.items()), prod_start):
        last_prod_row = idx
        avg_rate = data["rate_sum"] / data["rate_count"] if data["rate_count"] else 0
        ws1.cell(row=idx, column=1, value=name)
        ws1.cell(row=idx, column=2, value=data["qty"]).number_format = "#,##0.0"
        ws1.cell(row=idx, column=3, value=avg_rate).number_format = "₹#,##0.00"
        ws1.cell(row=idx, column=4, value=data["amount"]).number_format = "₹#,##0.00"

        for c in range(1, 5):
            cell = ws1.cell(row=idx, column=c)
            cell.font = font_regular
            cell.border = border_all
            if idx % 2 == 0:
                cell.fill = fill_zebra

    if last_prod_row >= prod_start:
        ws1.cell(row=last_prod_row + 1, column=1, value="Total").font = font_bold
        ws1.cell(row=last_prod_row + 1, column=2, value=f"=SUM(B{prod_start}:B{last_prod_row})").font = font_bold
        ws1.cell(row=last_prod_row + 1, column=4, value=f"=SUM(D{prod_start}:D{last_prod_row})").font = font_bold
        ws1.cell(row=last_prod_row + 1, column=4).number_format = "₹#,##0.00"

    ws2 = wb.create_sheet(title="Detailed Transactions")
    ws2.views.sheetView[0].showGridLines = True

    headers_det = ["Bill No", "Source File", "Date", "Particulars", "Qty", "Rate", "Amount"]
    for col_num, h in enumerate(headers_det, 1):
        c = ws2.cell(row=1, column=col_num, value=h)
        c.font = font_header
        c.fill = fill_header
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_all

    det_row = 2
    for bill_no, row in enumerate(normalized, 1):
        for item in row["items"]:
            name = str(item.get("name") or "").strip() or "Unknown"
            qty = safe_float(item.get("qty", 0))
            rate = safe_float(item.get("rate", 0))
            amount = safe_float(item.get("amount", 0))
            if amount <= 0 and qty > 0 and rate > 0:
                amount = qty * rate

            vals = [bill_no, row["source"], row["bill_date"], name, qty, rate, amount]
            for cidx, val in enumerate(vals, 1):
                cell = ws2.cell(row=det_row, column=cidx, value=val)
                cell.font = font_regular
                cell.border = border_all
                if det_row % 2 == 0:
                    cell.fill = fill_zebra

            ws2.cell(row=det_row, column=5).number_format = "#,##0.0"
            ws2.cell(row=det_row, column=6).number_format = "₹#,##0.00"
            ws2.cell(row=det_row, column=7).number_format = "₹#,##0.00"
            det_row += 1

    _auto_widths(ws1)
    _auto_widths(ws2)
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def process_single_file(uploaded_file, model_bundle, forced_provider):
    file_name = uploaded_file.name
    file_bytes = uploaded_file.getvalue()
    with st.status(f"Processing {file_name}", expanded=False) as status_box:
        status_box.write("Starting file analysis...")
        try:
            if file_name.lower().endswith(".pdf"):
                pages = convert_pdf_to_images(file_bytes)
                results = []
                for i, img in enumerate(pages):
                    status_box.write(f"Processing page {i + 1}/{len(pages)}")
                    data = analyze_with_auto_fallback(model_bundle, img, forced=forced_provider, file_name=file_name)
                    results.append({"page": i + 1, "source": file_name, "data": data})
                status_box.update(label=f"{file_name} processed successfully", state="complete", expanded=False)
                return results
            img = Image.open(BytesIO(file_bytes)).convert("RGB")
            data = analyze_with_auto_fallback(model_bundle, img, forced=forced_provider, file_name=file_name)
            status_box.update(label=f"{file_name} processed successfully", state="complete", expanded=False)
            return [{"page": 1, "source": file_name, "data": data}]
        except Exception as e:
            add_error("FILE_PROCESS", file_name, e)
            status_box.update(label=f"{file_name} failed", state="error", expanded=True)
            st.error(f"Error processing {file_name}: {e}")
            return []


def render_upload_module():
    st.markdown(
        """
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p>Automated structural data parsing pipeline powered by multiple providers.</p>
            </div>
            <div class="csc-meta-badge">📍 <b>Deep CSC</b><br>👤 Owner: Deepak | ID: 256423250015</div>
            <div class="branding-badge">Deep CSC AI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["📷 Scan / Upload", "🕘 History", "⚙️ Settings"])

    with tabs[0]:
        st.session_state.selected_provider = st.selectbox("Select OCR Provider", PROVIDERS, index=PROVIDERS.index(st.session_state.get("selected_provider", "Gemini")))
        uploaded_files = st.file_uploader("Upload Bill Images or PDFs", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

        c1, c2 = st.columns(2)
        with c1:
            process_now = st.button("Process All Files", use_container_width=True)
        with c2:
            clear_state = st.button("Clear Uploaded / Processed Files", use_container_width=True)

        if clear_state:
            st.session_state.processed_files = set()
            st.session_state.error_log = []
            st.session_state.file_statuses = []
            st.rerun()

        model_bundle = {
            "vision_client": setup_google_vision(),
            "gemini": setup_gemini(),
            "perplexity": setup_perplexity(),
            "openai": setup_openai(),
        }

        if uploaded_files and process_now:
            all_results = []
            prog = st.progress(0)
            total_files = len(uploaded_files)
            file_rows = []

            for idx_file, uploaded_file in enumerate(uploaded_files, 1):
                file_key = f"{uploaded_file.name}_{uploaded_file.size}"
                if file_key in st.session_state.processed_files:
                    file_rows.append({"file_name": uploaded_file.name, "status": "Skipped", "badge": get_status_badge_text("Skipped"), "note": "Already processed"})
                    prog.progress(idx_file / total_files)
                    continue

                try:
                    result_rows = process_single_file(uploaded_file, model_bundle, st.session_state.selected_provider)
                    all_results.extend(result_rows)

                    if result_rows:
                        file_rows.append({"file_name": uploaded_file.name, "status": "Success", "badge": ":green-badge[Success]", "note": f"{len(result_rows)} page(s) extracted"})
                    else:
                        file_rows.append({"file_name": uploaded_file.name, "status": "Failed", "badge": ":red-badge[Failed]", "note": "No usable output"})

                    st.session_state.processed_files.add(file_key)
                except Exception as e:
                    add_error("FILE_LOOP", uploaded_file.name, e)
                    file_rows.append({"file_name": uploaded_file.name, "status": "Failed", "badge": ":red-badge[Failed]", "note": str(e)})
                prog.progress(idx_file / total_files)

            if all_results:
                df = build_batch_summary(all_results)
                render_metrics(df)
                render_status_badges(df)

                st.markdown("### File Status")
                status_df = pd.DataFrame(file_rows)
                st.dataframe(status_df, use_container_width=True)

                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.dataframe(df, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

                render_error_panel()

                summary_text = make_share_text(df)
                s1, s2, s3 = st.columns(3)
                with s1:
                    st.link_button("📱 Share on WhatsApp", share_whatsapp(summary_text), use_container_width=True)
                with s2:
                    st.link_button("✈️ Share on Telegram", share_telegram(summary_text), use_container_width=True)
                with s3:
                    st.link_button("📧 Share by Email", share_email(summary_text), use_container_width=True)

                st.download_button(
                    "📥 Download Excel Report",
                    data=build_excel_export(all_results),
                    file_name="bill_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                render_error_panel()
                st.warning("No valid results produced. Check error panel for details.")

    with tabs[1]:
        st.subheader("Processing History")
        st.dataframe(get_history_df(), use_container_width=True)

    with tabs[2]:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        render_theme_toggle("settings")
        st.markdown("</div>", unsafe_allow_html=True)


def render_app():
    apply_theme_css()
    apply_css()
    if not st.session_state.logged_in:
        login_screen()
    else:
        with st.sidebar:
            st.markdown("### Controls")
            if st.button("Logout", use_container_width=True):
                logout()
            render_theme_toggle("sidebar")
            st.markdown("### Health")
            st.badge("OCR Ready", color="green", icon=":material/check_circle:")
            st.badge(f"Failures: {st.session_state.get('ocr_failures', 0)}", color="orange", icon=":material/error:")
        render_upload_module()


def main():
    setup_page()
    init_db()
    init_state()
    render_app()


if __name__ == "__main__":
    main()
