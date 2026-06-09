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
    from google.cloud import documentai
except Exception:
    documentai = None

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
        "gemini_available": True,
        "last_gemini_error_time": None,
        "gemini_cooldown_seconds": 900,
        "perplexity_enabled": True,
        "docai_enabled": True,
        "vision_enabled": True,
        "textract_enabled": True,
        "theme_mode": "light",
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
            .stDataFrame, .stMarkdown, .stText { color: #e5e7eb !important; }
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
def setup_perplexity():
    api_key = secret_or_default("PERPLEXITY_API_KEY", "").strip()
    if not api_key or OpenAI is None or "your_" in api_key.lower():
        return None
    return OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")


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


@st.cache_resource
def setup_docai():
    if documentai is None:
        return None, None
    project_id = secret_or_default("GCP_PROJECT_ID", "").strip()
    location = secret_or_default("DOC_AI_LOCATION", "us").strip()
    processor_id = secret_or_default("DOC_AI_PROCESSOR_ID", "").strip()
    if not project_id or not processor_id:
        return None, None
    client = documentai.DocumentProcessorServiceClient()
    return client, client.processor_path(project_id, location, processor_id)


def get_drive_service():
    service_account_file = secret_or_default("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if service_account is None or build is None or not os.path.exists(service_account_file):
        return None
    creds = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=["https://www.googleapis.com/auth/drive"],
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
    if not last_error:
        return True
    return (datetime.now() - last_error).total_seconds() >= st.session_state.get("gemini_cooldown_seconds", 900)


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
    for ln in lines[:10]:
        if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax)\b", ln, re.I):
            shop_name = ln[:80]
            break

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

    for p in [
        r"\bGrand Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"\bNet Total[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"\bTotal[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
        r"\bAmount[:\s]*₹?\s*([0-9,]+(?:\.\d{1,2})?)\b",
    ]:
        m = re.search(p, text, re.I)
        if m:
            total = m.group(1)
            break

    items = heuristic_extract_items(text)
    return {"shop_name": shop_name, "bill_date": bill_date, "gst_number": gst_number, "items": items, "total": total, "raw_text": text}


def try_gemini(model, image):
    try:
        resp = model.generate_content(
            [build_schema_prompt(), image],
            generation_config={"temperature": 0, "response_mime_type": "application/json"},
        )
        data = parse_json_from_response(getattr(resp, "text", ""))
        st.session_state.gemini_available = True
        st.session_state.last_gemini_error_time = None
        return data, None
    except Exception as e:
        if is_gemini_quota_error(e):
            st.session_state.gemini_available = False
            st.session_state.last_gemini_error_time = datetime.now()
        return None, e


def analyze_with_auto_fallback(model_bundle, image, forced=None):
    order = ["Gemini", "Google Vision OCR", "Google Document AI", "AWS Textract", "OpenAI", "Perplexity"]
    if forced in order:
        order = [forced] + [x for x in order if x != forced]

    for provider in order:
        try:
            if provider == "Gemini" and model_bundle.get("gemini") and can_try_gemini():
                data, _ = try_gemini(model_bundle["gemini"], image)
                if data:
                    return data

            elif provider == "Google Vision OCR" and model_bundle.get("vision_client") and st.session_state.get("vision_enabled", True):
                text = extract_vision_text(model_bundle["vision_client"], image)
                if text:
                    return heuristic_parse_from_text(text)

            elif provider == "Google Document AI" and model_bundle.get("docai_client") and model_bundle.get("docai_name") and st.session_state.get("docai_enabled", True):
                raw_document = documentai.RawDocument(content=image_to_bytes(image), mime_type="image/jpeg")
                request = documentai.ProcessRequest(name=model_bundle["docai_name"], raw_document=raw_document)
                result = model_bundle["docai_client"].process_document(request=request)
                text = getattr(result.document, "text", "") or ""
                if text:
                    return heuristic_parse_from_text(text)

            elif provider == "AWS Textract" and model_bundle.get("textract_client") and st.session_state.get("textract_enabled", True):
                resp = model_bundle["textract_client"].analyze_expense(Document={"Bytes": image_to_bytes(image)})
                text_parts = []
                for d in resp.get("ExpenseDocuments", []):
                    for sf in d.get("SummaryFields", []):
                        text_parts.append(
                            f"{sf.get('Type', {}).get('Text', '')}: {sf.get('ValueDetection', {}).get('Text', '')}"
                        )
                text = "\n".join(text_parts)
                if text:
                    return heuristic_parse_from_text(text)

            elif provider == "OpenAI" and model_bundle.get("openai"):
                b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
                resp = model_bundle["openai"].chat.completions.create(
                    model=secret_or_default("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": build_schema_prompt()},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract invoice JSON from this image."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                            ],
                        },
                    ],
                    response_format={"type": "json_object"},
                )
                return parse_json_from_response(resp.choices[0].message.content)

            elif provider == "Perplexity" and model_bundle.get("perplexity") and st.session_state.get("perplexity_enabled", True):
                b64 = base64.b64encode(image_to_bytes(image)).decode("utf-8")
                resp = model_bundle["perplexity"].chat.completions.create(
                    model=secret_or_default("PERPLEXITY_MODEL", "sonar-pro"),
                    messages=[
                        {"role": "system", "content": build_schema_prompt()},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract invoice JSON from this image."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                            ],
                        },
                    ],
                    temperature=0.0,
                )
                return parse_json_from_response(resp.choices[0].message.content)
        except Exception:
            continue

    return heuristic_parse_from_text("")


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


def render_bill_result(data, source_name, save_to_db=False, upload_drive=True):
    raw_text = str(data.get("raw_text") or "").strip() if isinstance(data, dict) else ""
    items = normalize_items(data.get("items") if isinstance(data, dict) else [])
    df = pd.DataFrame(items) if items else pd.DataFrame(columns=["name", "qty", "rate", "amount"])

    shop_name = str(data.get("shop_name") or "").strip() if isinstance(data, dict) else ""
    bill_date = str(data.get("bill_date") or "").strip() if isinstance(data, dict) else ""
    gst_number = data.get("gst_number") if isinstance(data, dict) else None
    gst_number = gst_number or "N/A"

    if not shop_name and raw_text:
        for ln in [x.strip() for x in raw_text.splitlines() if x.strip()][:10]:
            if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax)\b", ln, re.I):
                shop_name = ln[:80]
                break
    if not shop_name:
        shop_name = "Unknown Shop"
    if not bill_date:
        bill_date = datetime.now().strftime("%Y-%m-%d")

    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        calculated_total = float(df["amount"].sum())
    else:
        calculated_total = 0.0
        st.info("No items detected.")

    bill_total = safe_float(data.get("total", 0) if isinstance(data, dict) else 0)
    has_meaningful_data = bool(raw_text) or not df.empty or bill_total > 0 or shop_name != "Unknown Shop"
    status = "Needs Review"
    if has_meaningful_data and bill_total > 0 and abs(calculated_total - bill_total) < 1:
        status = "Matched"
    elif has_meaningful_data and bill_total > 0:
        status = "Mismatch"

    st.markdown(f"### 🏪 Vendor: `{shop_name}`")
    c1, c2 = st.columns(2)
    c1.markdown(f"**🗓️ Declared Invoice Date:** {bill_date}")
    is_valid_gst, formatted_gst = validate_gst(gst_number)
    if gst_number != "N/A":
        c2.markdown(f"**🛡️ GSTIN Registry Validation:** {'✅ Valid - ' + formatted_gst if is_valid_gst else '⚠️ Format Mismatch - ' + formatted_gst}")
    else:
        c2.markdown("**🛡️ GSTIN Registry Validation:** ℹ️ Not Disclosed")

    st.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
    st.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")
    diff = abs(calculated_total - bill_total)
    st.success("🎯 Auto-Arithmetic Audit Pass." if diff < 1 else f"🛑 Audit Discrepancy Found: ₹{diff:,.2f}")
    st.info(f"Status: {status}")

    if raw_text:
        with st.expander("View extracted raw text"):
            st.text(raw_text[:20000])

    if save_to_db:
        insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status)

    if upload_drive:
        try:
            out_json = os.path.join(OUTPUT_DIR, f"bill_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            payload = {
                "shop_name": shop_name,
                "bill_date": bill_date,
                "gst_number": gst_number,
                "items": items,
                "total": bill_total,
                "calculated_total": calculated_total,
                "status": status,
                "source": source_name,
                "timestamp": datetime.now().isoformat(),
                "raw_text": raw_text,
            }
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            uploaded = upload_to_drive(out_json, drive_name=os.path.basename(out_json), mime_type="application/json")
            if uploaded:
                st.success(f"Google Drive upload done: {uploaded.get('name', 'file')}")
        except Exception as e:
            st.warning(f"Drive upload skipped: {e}")


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
            has_meaningful_data = bool(raw_text) or not tmp_df.empty or total > 0 or shop != "Unknown Shop"
            if not has_meaningful_data:
                status = "Needs Review"
            else:
                status = "Matched" if total > 0 and abs(calc_total - total) < 1 else ("Mismatch" if total > 0 else "Needs Review")
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


def sanitize_sheet_name(name, fallback="Sheet"):
    name = re.sub(r"[\[\]\*\?/\\:]", "_", str(name)).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:31] or fallback)


def build_excel_export(results):
    buffer = BytesIO()
    summary_rows = []

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for idx, item in enumerate(results, start=1):
            d = item.get("data") or {}
            raw_text = str(d.get("raw_text") or "").strip()
            items = normalize_items(d.get("items"))

            shop = str(d.get("shop_name") or "").strip()
            if not shop and raw_text:
                for ln in [x.strip() for x in raw_text.splitlines() if x.strip()][:10]:
                    if len(ln) >= 3 and not re.search(r"\b(invoice|bill|gst|date|total|amount|tax)\b", ln, re.I):
                        shop = ln[:80]
                        break
            if not shop:
                shop = f"Bill_{idx}"

            bill_date = str(d.get("bill_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
            gst_number = d.get("gst_number") or "N/A"
            bill_total = safe_float(d.get("total", 0))

            tmp_df = pd.DataFrame(items) if items else pd.DataFrame(columns=["name", "qty", "rate", "amount"])
            if not tmp_df.empty and "amount" in tmp_df.columns:
                tmp_df["amount"] = pd.to_numeric(tmp_df["amount"], errors="coerce").fillna(0)
                calculated_total = float(tmp_df["amount"].sum())
            else:
                calculated_total = 0.0

            has_meaningful_data = bool(raw_text) or not tmp_df.empty or bill_total > 0
            if not has_meaningful_data:
                status = "Needs Review"
            else:
                status = "Matched" if bill_total > 0 and abs(calculated_total - bill_total) < 1 else ("Mismatch" if bill_total > 0 else "Needs Review")

            base_name = sanitize_sheet_name(f"{idx}_{shop}")
            items_sheet = base_name
            meta_sheet = sanitize_sheet_name(f"{base_name}_meta")
            text_sheet = sanitize_sheet_name(f"{base_name}_text")

            tmp_df.to_excel(writer, sheet_name=items_sheet, index=False)

            meta_df = pd.DataFrame([{
                "page": item.get("page"),
                "source": item.get("source"),
                "shop_name": shop,
                "bill_date": bill_date,
                "gst_number": gst_number,
                "declared_total": bill_total,
                "calculated_total": calculated_total,
                "difference": abs(calculated_total - bill_total),
                "status": status
            }])
            meta_df.to_excel(writer, sheet_name=meta_sheet, index=False)

            if raw_text:
                pd.DataFrame({"raw_text": [raw_text]}).to_excel(writer, sheet_name=text_sheet, index=False)

            summary_rows.append({
                "bill_no": idx,
                "source": item.get("source"),
                "shop_name": shop,
                "bill_date": bill_date,
                "gst_number": gst_number,
                "declared_total": bill_total,
                "calculated_total": calculated_total,
                "difference": abs(calculated_total - bill_total),
                "status": status,
                "sheet_name": items_sheet
            })

        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)

    buffer.seek(0)
    return buffer.getvalue()


def render_theme_toggle(location="main"):
    mode = st.radio(
        "Theme",
        ["light", "dark"],
        horizontal=True,
        index=0 if st.session_state.get("theme_mode", "light") == "light" else 1,
        key=f"theme_radio_{location}",
    )
    if mode != st.session_state.get("theme_mode", "light"):
        st.session_state["theme_mode"] = mode
        st.rerun()


def render_upload_module():
    st.markdown(
        """
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by multiple providers.</p>
            </div>
            <div class="csc-meta-badge">📍 <b>Deep CSC</b><br>👤 Owner: Deepak | ID: 256423250015</div>
            <div class="branding-badge">Deep CSC AI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["📷 Scan / Upload", "🕘 History", "⚙️ Settings"])

    with tabs[0]:
        providers = ["Google Vision OCR", "Google Document AI", "AWS Textract", "Gemini", "OpenAI", "Perplexity"]
        st.session_state.selected_provider = st.selectbox("Select OCR Provider", providers, index=providers.index("Gemini"), key="provider_selectbox")
        uploaded_file = st.file_uploader("Upload Bill Image or PDF", type=["jpg", "jpeg", "png", "pdf"])

        vision_client = setup_google_vision()
        gemini_model = setup_gemini()
        openai_client = setup_openai()
        perplexity_client = setup_perplexity()
        textract_client = setup_textract()
        docai_client, docai_name = setup_docai()

        model_bundle = {
            "vision_client": vision_client,
            "docai_client": docai_client,
            "docai_name": docai_name,
            "gemini": gemini_model,
            "openai": openai_client,
            "perplexity": perplexity_client,
            "textract_client": textract_client,
        }

        if uploaded_file:
            file_bytes = uploaded_file.read()
            if uploaded_file.name.lower().endswith(".pdf"):
                if st.button("Process PDF", use_container_width=True):
                    try:
                        pages = convert_pdf_to_images(file_bytes)
                    except Exception as e:
                        st.error(f"PDF convert nahi ho paaya: {e}")
                        pages = []

                    results = []
                    for idx, page_img in enumerate(pages, start=1):
                        try:
                            data = analyze_with_auto_fallback(model_bundle, page_img, forced=st.session_state.get("selected_provider"))
                            results.append({"page": idx, "source": uploaded_file.name, "data": data, "error": None})
                        except Exception as e:
                            results.append({"page": idx, "source": uploaded_file.name, "data": None, "error": str(e)})

                    df = build_batch_summary(results)
                    st.dataframe(df, use_container_width=True, hide_index=True)

                    excel_data = build_excel_export(results)
                    st.download_button(
                        label="📥 Download Excel with Separate Bills + Summary",
                        data=excel_data,
                        file_name="bills_separate_summary.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                image = Image.open(BytesIO(file_bytes)).convert("RGB")
                st.image(image, caption="Uploaded Bill", use_container_width=True)
                if st.button("Process Image", use_container_width=True):
                    data = analyze_with_auto_fallback(model_bundle, image, forced=st.session_state.get("selected_provider"))
                    render_bill_result(data, uploaded_file.name, save_to_db=True, upload_drive=True)

                    single_results = [{
                        "page": 1,
                        "source": uploaded_file.name,
                        "data": data,
                        "error": None
                    }]

                    excel_data = build_excel_export(single_results)
                    st.download_button(
                        label="📥 Download Excel with Summary",
                        data=excel_data,
                        file_name="single_bill_summary.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

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
        st.caption("Provider order is sequential and fail-fast for speed.")


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
