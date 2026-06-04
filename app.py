import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageOps, ImageFilter
import pandas as pd
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import tempfile
import json
import re
import sqlite3
from datetime import datetime
import numpy as np
from pdf2image import convert_from_bytes

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from paddleocr import PaddleOCR
except Exception:
    PaddleOCR = None

try:
    import easyocr
except Exception:
    easyocr = None

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
DEFAULT_USERNAME = st.secrets.get("APP_USERNAME", "admin")
DEFAULT_PASSWORD = st.secrets.get("APP_PASSWORD", "password123")

def setup_page():
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide", initial_sidebar_state="expanded")

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
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO bills
            (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        return False
    finally:
        if conn:
            conn.close()

def init_auth():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def init_runtime_state():
    if "gemini_available" not in st.session_state:
        st.session_state.gemini_available = True
    if "last_gemini_error_time" not in st.session_state:
        st.session_state.last_gemini_error_time = None
    if "gemini_cooldown_seconds" not in st.session_state:
        st.session_state.gemini_cooldown_seconds = 900
    if "gemini_retry_count" not in st.session_state:
        st.session_state.gemini_retry_count = 0

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
        st.error("Please configure GEMINI_API_KEY in your Streamlit secrets.")
        st.stop()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

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
    cooldown = st.session_state.get("gemini_cooldown_seconds", 900)
    return (datetime.now() - last_error).total_seconds() >= cooldown

def preprocess_for_ocr(image):
    if not isinstance(image, Image.Image):
        image = Image.open(image)
    image = image.convert("RGB")
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    gray = gray.resize((gray.width * 2, gray.height * 2))
    arr = np.array(gray, dtype=np.float32)
    arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-6) * 255.0
    arr = np.clip(arr, 0, 255).astype("uint8")
    img = Image.fromarray(arr)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    return img

def extract_page_text_from_image(image):
    if pytesseract is None:
        return ""
    processed = preprocess_for_ocr(image)
    configs = ["--psm 6", "--psm 11", "--psm 4"]
    texts = []
    for cfg in configs:
        try:
            txt = pytesseract.image_to_string(processed, config=cfg)
            if txt and txt.strip():
                texts.append(txt)
        except Exception:
            pass
    return max(texts, key=len, default="")

def local_ocr_from_image(image):
    if pytesseract is None:
        raise RuntimeError("pytesseract not available")
    return extract_page_text_from_image(image)

def local_ocr_from_pdf(pdf_bytes):
    pages = convert_from_bytes(pdf_bytes, dpi=300)
    texts = []
    for page in pages:
        texts.append(local_ocr_from_image(page))
    return "\n".join(texts)

def run_paddleocr(image_or_pdf_bytes, source_type="image"):
    if PaddleOCR is None:
        raise RuntimeError("PaddleOCR not installed")
    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    texts = []
    if source_type == "pdf":
        pages = convert_from_bytes(image_or_pdf_bytes, dpi=300)
        for page in pages:
            result = ocr.ocr(np.array(page), cls=True)
            for line in result[0] if result and result[0] else []:
                texts.append(line[1][0])
    else:
        img = image_or_pdf_bytes if isinstance(image_or_pdf_bytes, Image.Image) else Image.open(image_or_pdf_bytes)
        result = ocr.ocr(np.array(img), cls=True)
        for line in result[0] if result and result[0] else []:
            texts.append(line[1][0])
    return "\n".join(texts)

def run_easyocr(image_or_pdf_bytes, source_type="image"):
    if easyocr is None:
        raise RuntimeError("EasyOCR not installed")
    reader = easyocr.Reader(['en'], gpu=False)
    texts = []
    if source_type == "pdf":
        pages = convert_from_bytes(image_or_pdf_bytes, dpi=300)
        for page in pages:
            result = reader.readtext(np.array(page), detail=0)
            texts.extend(result)
    else:
        img = image_or_pdf_bytes if isinstance(image_or_pdf_bytes, Image.Image) else Image.open(image_or_pdf_bytes)
        result = reader.readtext(np.array(img), detail=0)
        texts.extend(result)
    return "\n".join(texts)

def run_tesseract(image_or_pdf_bytes, source_type="image"):
    if pytesseract is None:
        raise RuntimeError("pytesseract not installed")
    if source_type == "pdf":
        return local_ocr_from_pdf(image_or_pdf_bytes)
    return local_ocr_from_image(image_or_pdf_bytes)

def parse_bill_text_locally(text):
    text = text or ""
    if not text.strip():
        return {"shop_name": None, "bill_date": None, "gst_number": None, "items": [], "total": None, "_raw_text": ""}

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    shop_name = None
    for ln in lines[:10]:
        clean = re.sub(r'[^A-Za-z0-9&.,()/-\s]', ' ', ln).strip()
        if len(clean) >= 3 and not re.search(r'\b(total|amount|date|invoice|gst|tax|qty|rate|hsn|memo|cash)\b', clean, re.IGNORECASE):
            shop_name = clean[:60]
            break
    if not shop_name and lines:
        shop_name = lines[0][:60]

    bill_date = None
    for pat in [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})',
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})'
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            bill_date = m.group(1)
            break

    gst_number = None
    gst_match = re.search(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z]\d\b', text.upper())
    if gst_match:
        gst_number = gst_match.group(0)

    total = None
    for pat in [
        r'(?:grand\s*total|net\s*amount|total\s*amount|amount\s*due|invoice\s*total|final\s*total|total)\s*[:\-]?\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)',
        r'₹\s*([0-9,]+(?:\.[0-9]{1,2})?)'
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            total = m.group(1)
            break

    items = []
    for ln in lines:
        if re.search(r'\b(qty|rate|amount|particulars)\b', ln, re.IGNORECASE):
            continue
        if re.search(r'\d', ln) and len(ln) > 8:
            items.append({"name": ln[:80], "qty": "", "rate": "", "amount": ""})

    return {
        "shop_name": shop_name,
        "bill_date": bill_date,
        "gst_number": gst_number,
        "items": items[:25],
        "total": total,
        "_raw_text": text
    }

def analyze_gemini(model, file_payload):
    prompt = """
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
    response = model.generate_content([prompt, file_payload])
    return parse_json_from_response(getattr(response, "text", ""))

def score_ocr_text(text):
    score = 0
    t = (text or "").lower()
    if "total" in t:
        score += 4
    if "invoice" in t:
        score += 3
    if "gst" in t:
        score += 3
    if "qty" in t or "quantity" in t:
        score += 2
    if "rate" in t:
        score += 2
    if "amount" in t:
        score += 2
    if "memo" in t or "cash" in t:
        score += 1
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", t):
        score += 2
    if len(text.strip()) > 80:
        score += 1
    return score

def merge_ocr_results(ocr_runs):
    best_text = ""
    best_score = -1
    for _, text in ocr_runs:
        if not text or str(text).startswith("ERROR:"):
            continue
        score = score_ocr_text(text)
        if score > best_score:
            best_score = score
            best_text = text
    if not best_text.strip():
        best_text = "\n".join([t for _, t in ocr_runs if isinstance(t, str) and t and not t.startswith("ERROR:")])
    return parse_bill_text_locally(best_text)

def analyze_with_local_chain(image_or_pdf, source_type="image"):
    ocr_runs = []
    try:
        if source_type == "pdf":
            pages = convert_from_bytes(image_or_pdf, dpi=300)
            page_texts = [extract_page_text_from_image(page) for page in pages]
            ocr_runs.append(("Tesseract", "\n".join(page_texts)))
        else:
            ocr_runs.append(("Tesseract", extract_page_text_from_image(image_or_pdf)))
    except Exception as ex:
        ocr_runs.append(("Tesseract", f"ERROR: {ex}"))

    try:
        ocr_runs.append(("PaddleOCR", run_paddleocr(image_or_pdf, source_type)))
    except Exception as ex:
        ocr_runs.append(("PaddleOCR", f"ERROR: {ex}"))

    try:
        ocr_runs.append(("EasyOCR", run_easyocr(image_or_pdf, source_type)))
    except Exception as ex:
        ocr_runs.append(("EasyOCR", f"ERROR: {ex}"))

    result = merge_ocr_results(ocr_runs)
    best_raw = ""
    for _, txt in ocr_runs:
        if isinstance(txt, str) and txt and not txt.startswith("ERROR:") and len(txt) > len(best_raw):
            best_raw = txt
    result["_raw_text"] = best_raw
    result["_ocr_runs"] = {k: v for k, v in ocr_runs}
    return result

def analyze_with_auto_fallback(model, image_or_pdf, source_type="image"):
    if can_try_gemini():
        try:
            result = analyze_gemini(model, image_or_pdf)
            st.session_state.gemini_available = True
            st.session_state.last_gemini_error_time = None
            st.session_state.gemini_retry_count = 0
            return result
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "quota" in msg or "rate limit" in msg:
                st.session_state.gemini_available = False
                st.session_state.last_gemini_error_time = datetime.now()
                st.session_state.gemini_retry_count += 1
                st.warning("Gemini quota exhausted. Switching to local OCR fallback.")
            else:
                raise
    return analyze_with_local_chain(image_or_pdf, source_type)

def render_bill_result(data, source_name, save_to_db=False):
    if not isinstance(data, dict):
        st.error("AI se data nahi mil paaya.")
        return

    with st.expander("🧪 OCR Debug Output", expanded=False):
        st.write("Raw OCR text:")
        st.code(data.get("_raw_text", ""), language="text")
        st.write("OCR engine outputs:")
        st.json(data.get("_ocr_runs", {}))

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
        calculated_total = 0.0
        df = pd.DataFrame(columns=["name", "qty", "rate", "amount"])
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
    st.download_button("📥 Export Excel Data Sheets", data=excel_buffer.getvalue(), file_name=f"{safe_shop}_ledger.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"excel_{safe_source}")

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
        st.download_button("📄 Download Sign-off PDF", f.read(), file_name=f"{safe_shop}_receipt.pdf", mime="application/pdf", use_container_width=True, key=f"pdf_{safe_source}")

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
            rows.append({"page": item.get("page"), "source": item.get("source"), "shop_name": shop_name, "bill_date": bill_date, "gst_number": gst_number, "bill_total": bill_total, "calculated_total": calculated_total, "difference": diff, "status": status_txt})
        else:
            rows.append({"page": item.get("page"), "source": item.get("source"), "shop_name": None, "bill_date": None, "gst_number": None, "bill_total": None, "calculated_total": None, "difference": None, "status": f"Error: {item.get('error')}"})
    return pd.DataFrame(rows)

def make_excel_download(df, filename, label="📥 Download Excel", key="excel_download"):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Batch Summary")
    st.download_button(label, data=buffer.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=key)

def process_pdf_pages(model, pdf_bytes, source_name):
    results = []
    pages = convert_from_bytes(pdf_bytes, dpi=300)
    for p_idx, page_img in enumerate(pages, start=1):
        try:
            data = analyze_with_auto_fallback(model, page_img, source_type="image")
            results.append({"page": p_idx, "source": source_name, "data": data, "error": None})
        except Exception as e:
            results.append({"page": p_idx, "source": source_name, "data": None, "error": str(e)})
    return results

def render_upload_module(model):
    st.markdown('<div class="deep-csc-header"><div class="branding-text"><h1>🧾 AI Multi-Bill OCR Processor</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by Gemini Vision Core.</p></div><div class="csc-meta-badge">📍 <b>Deep Digital Seva Kendra</b><br>👤 Owner: Deepak | ID: 256423250015</div><div class="branding-badge">Deep CSC AI</div></div>', unsafe_allow_html=True)

    if st.button("🔄 Retry Gemini Now", key="retry_gemini", use_container_width=True):
        st.session_state.gemini_available = True
        st.session_state.last_gemini_error_time = None
        st.session_state.gemini_retry_count = 0
        st.success("Gemini retry enabled. Next request will try Gemini first.")

    uploaded_files = st.file_uploader("Drop batch bill images or PDF files below (Multi-upload supported)", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)
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
                pages = convert_from_bytes(pdf_bytes, dpi=300)
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
                st.image(page_img, caption=f"{file.name} - Page {p_idx}", use_container_width=True)

            if results:
                st.markdown("## 📋 Page-wise Consolidated Summary")
                summary_df = build_batch_summary(results)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                make_excel_download(summary_df, f"{file.name}_page_wise_summary.xlsx", label="📥 Download Batch Excel", key=f"batch_excel_{idx}")

                st.markdown("## ✅ Batch Results")
                for item in results:
                    if item["error"]:
                        err = item["error"]
                        if "quota" in err.lower() or "429" in err:
                            st.warning(f"Page {item['page']}: Gemini quota limit reached.")
                        else:
                            st.error(f"Page {item['page']}: {err}")
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
                            data = analyze_with_auto_fallback(model, image, source_type="image")
                            render_bill_result(data, file.name, save_to_db=True)
                        except Exception as e:
                            st.error(f"Structural Parsing Fault: {e}")

def main():
    setup_page()
    apply_css()
    init_db()
    init_auth()
    init_runtime_state()
    model = setup_gemini()

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
        st.markdown(f"<p style='color:#cbd5e1; font-size:13px; margin-left:5px;'>Gemini state: <b>{'Available' if st.session_state.gemini_available else 'Fallback mode'}</b></p>", unsafe_allow_html=True)
        st.selectbox("Navigate System", ["📤 Upload & Process"], key="app_mode")
        st.markdown("<br><br><hr style='border-color: #1e293b;'>", unsafe_allow_html=True)
        if st.button("🚪 Terminate Session", use_container_width=True, key="terminate_session"):
            terminate_session()

    render_upload_module(model)

if __name__ == "__main__":
    main()
