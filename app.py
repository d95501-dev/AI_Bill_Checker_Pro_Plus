import base64
import json
import os
import re
import sqlite3
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

# Openpyxl for premium excel rendering
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
        .deep-csc-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            padding: 30px; border-radius: 24px; margin-bottom: 20px;
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
            text-transform: uppercase; letter-spacing: 1px;
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
    name = re.sub(r"[\[\]\*\?/\\:]", "_", str(name)).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:31] or fallback)


# PREMIUM EXCEL GENERATOR (DYNAMIC FORMULAS & CLASSIC NAVY THEME)
def build_excel_export(results):
    buffer = BytesIO()
    wb = openpyxl.Workbook()
    
    # 1. Main Overview Summary Tab Setup
    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.views.sheetView[0].showGridLines = True
    
    # Classic Navy Theme Constants
    navy_dark = "1B365D"
    navy_light = "F0F4F8"
    border_gray = "D3D3D3"
    white = "FFFFFF"
    
    font_title = Font(name="Calibri", size=16, bold=True, color=navy_dark)
    font_header = Font(name="Calibri", size=11, bold=True, color=white)
    font_bold = Font(name="Calibri", size=11, bold=True)
    font_regular = Font(name="Calibri", size=11)
    
    fill_header = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
    fill_zebra = PatternFill(start_color=navy_light, end_color=navy_light, fill_type="solid")
    
    thin_side = Side(style='thin', color=border_gray)
    border_data = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    border_total = Border(top=Side(style='thin', color='000000'), bottom=Side(style='double', color='000000'))
    
    ws_summary["A1"] = "BATCH BILL PROCESSING OVERVIEW"
    ws_summary["A1"].font = font_title
    
    summary_headers = ["Bill No.", "Source File", "Shop Name", "Bill Date", "GST Number", "Declared Total (₹)", "Calculated Total (₹)", "Difference (₹)", "Status", "Sheet Link"]
    for col_idx, text in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row=3, column=col_idx, value=text)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 2. Iterate results and build separate formatted tabs
    for idx, item in enumerate(results, start=1):
        d = item.get("data") or {}
        raw_text = str(d.get("raw_text") or "").strip()
        items = normalize_items(d.get("items"))
        
        shop = str(d.get("shop_name") or "").strip() or f"Bill_{idx}"
        bill_date = str(d.get("bill_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
        gst_number = d.get("gst_number") or "N/A"
        bill_total = safe_float(d.get("total", 0))
        
        base_name = sanitize_sheet_name(f"{idx}_{shop}")
        ws_item = wb.create_sheet(title=base_name)
        ws_item.views.sheetView[0].showGridLines = True
        
        # Individual Sheet Metadata Area
        ws_item["A1"] = "INVOICE RECORD BREAKDOWN"
        ws_item["A1"].font = font_title
        
        meta_info = [
            ("Shop/Vendor Name:", shop, "Bill Date:", bill_date),
            ("GSTIN Number:", gst_number, "Source File:", item.get("source", "N/A"))
        ]
        for r_offset, row_data in enumerate(meta_info, 3):
            ws_item.cell(row=r_offset, column=1, value=row_data[0]).font = font_bold
            ws_item.cell(row=r_offset, column=2, value=row_data[1]).font = font_regular
            ws_item.cell(row=r_offset, column=4, value=row_data[2]).font = font_bold
            ws_item.cell(row=r_offset, column=5, value=row_data[3]).font = font_regular

        # Item Headers
        item_headers = ["Sr. No.", "Particulars", "Quantity (No.)", "Rate (₹)", "Billed Amount (₹)", "Calculated Amount (₹)", "Status Check"]
        item_header_row = 6
        for col_idx, text in enumerate(item_headers, 1):
            cell = ws_item.cell(row=item_header_row, column=col_idx, value=text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Write Items List
        curr_row = item_header_row + 1
        for s_no, it in enumerate(items, start=1):
            ws_item.cell(row=curr_row, column=1, value=s_no).alignment = Alignment(horizontal="center")
            ws_item.cell(row=curr_row, column=2, value=it.get("name", ""))
            ws_item.cell(row=curr_row, column=3, value=safe_float(it.get("qty", 0))).number_format = '#,##0'
            ws_item.cell(row=curr_row, column=4, value=safe_float(it.get("rate", 0))).number_format = '#,##0.00'
            ws_item.cell(row=curr_row, column=5, value=safe_float(it.get("amount", 0))).number_format = '#,##0.00'
            
            # Auto Formula Injection
            ws_item.cell(row=curr_row, column=6, value=f"=C{curr_row}*D{curr_row}").number_format = '#,##0.00'
            ws_item.cell(row=curr_row, column=7, value=f'=IF(E{curr_row}=F{curr_row},"Match","Mismatch")').alignment = Alignment(horizontal="center")
            
            for c in range(1, 8):
                cell = ws_item.cell(row=curr_row, column=c)
                cell.font = font_regular
                cell.border = border_data
                if curr_row % 2 == 0:
                    cell.fill = fill_zebra
            curr_row += 1

        # Sheet Summary Blocks
        curr_row += 1
        ws_item.cell(row=curr_row, column=2, value="Total Boarding Charges Summary").font = font_bold
        ws_item.cell(row=curr_row, column=5, value=bill_total).font = font_bold
        ws_item.cell(row=curr_row, column=5).number_format = '#,##0.00'
        ws_item.cell(row=curr_row, column=6, value=f"=SUM(F{item_header_row+1}:F{curr_row-2})").font = font_bold
        ws_item.cell(row=curr_row, column=6).number_format = '#,##0.00'
        ws_item.cell(row=curr_row, column=5).border = border_total
        ws_item.cell(row=curr_row, column=6).border = border_total

        # Populate Global Summary Line row
        s_row = 3 + idx
        ws_summary.cell(row=s_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws_summary.cell(row=s_row, column=2, value=item.get("source"))
        ws_summary.cell(row=s_row, column=3, value=shop)
        ws_summary.cell(row=s_row, column=4, value=bill_date).alignment = Alignment(horizontal="center")
        ws_summary.cell(row=s_row, column=5, value=gst_number)
        ws_summary.cell(row=s_row, column=6, value=bill_total).number_format = '#,##0.00'
        
        # Cross reference formula connecting directly to the child tab
        ws_summary.cell(row=s_row, column=7, value=f"='{base_name}'!F{curr_row}").number_format = '#,##0.00'
        ws_summary.cell(row=s_row, column=8, value=f"=ABS(F{s_row}-G{s_row})").number_format = '#,##0.00'
        ws_summary.cell(row=s_row, column=9, value=f'=IF(H{s_row}<1,"Matched","Mismatch")').alignment = Alignment(horizontal="center")
        
        # Hyperlink to specific tab
        link_cell = ws_summary.cell(row=s_row, column=10, value="Go To Breakdown Sheet")
        link_cell.hyperlink = f"#'{base_name}'!A1"
        link_cell.font = Font(name="Calibri", size=11, color="0000FF", underline="single")
        link_cell.alignment = Alignment(horizontal="center")

        for c in range(1, 11):
            cell = ws_summary.cell(row=s_row, column=c)
            if not cell.font.color:
                cell.font = font_regular
            cell.border = border_data
            if s_row % 2 == 0:
                cell.fill = fill_zebra

        # Also push data to local SQLite DB for monitoring
        try:
            status_text = "Matched" if abs(safe_float(ws_item.cell(row=curr_row, column=6).value) - bill_total) < 1 else "Mismatch"
            insert_bill(shop, bill_date, gst_number, bill_total, safe_float(bill_total), status_text)
        except Exception:
            pass

    # Dynamic Column Width Auto-Fitting
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    val_str = str(cell.value)
                    if not val_str.startswith("="):
                        max_len = max(max_len, len(val_str))
                    else:
                        max_len = max(max_len, 15)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def build_batch_summary(results):
    rows = []
    for item in results:
        d = item.get("data")
        if d:
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


def render_upload_module():
    st.markdown("""
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by multiple providers.</p>
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
        with col_a:
            process_now = st.button("Process All Files", use_container_width=True)
        with col_b:
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
                name_lower = uploaded_file.name.lower()

                if name_lower.endswith(".pdf"):
                    try:
                        pages = convert_pdf_to_images(file_bytes)
                    except Exception as e:
                        st.error(f"{uploaded_file.name} PDF convert nahi ho paaya: {e}")
                        pages = []
                else:
                    try:
                        pages = [Image.open(BytesIO(file_bytes)).convert("RGB")]
                    except Exception as e:
                        st.error(f"{uploaded_file.name} image open nahi ho paayi: {e}")
                        pages = []

                for idx, page_img in enumerate(pages, start=1):
                    try:
                        data = analyze_with_auto_fallback(
                            model_bundle,
                            page_img,
                            forced=st.session_state.get("selected_provider")
                        )
                        all_results.append({"page": idx, "source": uploaded_file.name, "data": data, "error": None})
                    except Exception as e:
                        all_results.append({"page": idx, "source": uploaded_file.name, "data": None, "error": str(e)})

                st.session_state.processed_files.add(file_key)

            if all_results:
                summary_df = build_batch_summary(all_results)
                st.subheader("Combined Summary")
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

                st.download_button(
                    "📥 Download Combined Excel with Separate Bills + Summary",
                    data=build_excel_export(all_results),
                    file_name="combined_bills_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        elif uploaded_files and not process_now:
            st.info("Files uploaded hain. Process All Files button dabao.")

    with tabs[1]:
        st.subheader("History")
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            df = pd.read_sql_query(
                "SELECT shop_name, bill_date, gst_number, total, calculated_total, status, timestamp FROM bills ORDER BY id DESC LIMIT 50",
                conn
            )
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Settings")
        st.caption("Theme control is available in the sidebar.")
        st.caption("Provider order: Gemini -> Google Vision OCR -> Perplexity -> OpenAI.")


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
        st.markdown("""
            <div style="padding:12px;border:1px solid rgba(255,255,255,0.14);border-radius:14px;">
                <div style="font-size:22px;font-weight:800;">Deep CSC</div>
                <div style="font-size:16px;font-weight:700;margin-top:4px;">AI Bill Processor</div>
                <div style="font-size:13px;opacity:0.95;margin-top:8px;">ID: 256423250015</div>
                <div style="font-size:12px;opacity:0.9;margin-top:10px;">Provider-ready OCR and invoice processing dashboard.</div>
            </div>
        """, unsafe_allow_html=True)
        render_theme_toggle("sidebar")
        if st.button("Logout", use_container_width=True):
            terminate_session()

    render_upload_module()


if __name__ == "__main__":
    main()
