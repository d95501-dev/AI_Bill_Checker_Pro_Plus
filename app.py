# ==========================================================
# DEEP CSC AI BILL PROCESSOR PREMIUM ENTERPRISE
# PART 1 - FOUNDATION LAYER
# ==========================================================

import subprocess
from pathlib import Path
import streamlit as st
import google.generativeai as genai

from PIL import Image
from io import BytesIO

import pandas as pd
import sqlite3
import hashlib
import json
import re
import os
import time
import tempfile
import urllib.parse
import platform

from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet
)

# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="Deep CSC AI Bill Processor Premium",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================================
# ENVIRONMENT DETECTION
# ==========================================================

IS_LOCAL = 
NAPS2_PATH = r"C:\Program Files\NAPS2\NAPS2.Console.exe"

def scan_document(dpi=300):

    output_file = "scan.jpg"

    if not os.path.exists(NAPS2_PATH):
        return None

    cmd = [
        NAPS2_PATH,
        "--driver", "wia",
        "--device", "Brother DCP-T820DW",
        "--source", "glass",
        "--dpi", str(dpi),
        "-o", output_file,
        "-f"
    ]

    try:

        subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        if os.path.exists(output_file):
            return output_file

    except Exception:
        pass

    return None
(
    platform.system() == "Windows"
    and os.path.exists(
        r"C:\Program Files\NAPS2\NAPS2.Console.exe"
    )
)

# ==========================================================
# SESSION VARIABLES
# ==========================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "current_bill" not in st.session_state:
    st.session_state.current_bill = None

if "fraud_score" not in st.session_state:
    st.session_state.fraud_score = 0

# ==========================================================
# DATABASE INITIALIZATION
# ==========================================================

def init_db():

    conn = sqlite3.connect("bills.db")

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bills (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        image_hash TEXT,

        shop_name TEXT,

        bill_date TEXT,

        gst_number TEXT,

        category TEXT,

        total REAL,

        calculated_total REAL,

        fraud_score REAL,

        status TEXT,

        timestamp TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ==========================================================
# HASH GENERATOR
# ==========================================================

def generate_hash(file_bytes):

    return hashlib.md5(
        file_bytes
    ).hexdigest()

# ==========================================================
# DUPLICATE CHECK
# ==========================================================

def check_duplicate(image_hash):

    conn = sqlite3.connect("bills.db")

    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM bills
        WHERE image_hash = ?
        """,
        (image_hash,)
    )

    result = cur.fetchone()

    conn.close()

    return result is not None

# ==========================================================
# SAVE BILL
# ==========================================================

def save_bill(
    image_hash,
    shop_name,
    bill_date,
    gst_number,
    category,
    total,
    calculated_total,
    fraud_score,
    status
):

    conn = sqlite3.connect("bills.db")

    cur = conn.cursor()

    cur.execute("""
    INSERT INTO bills (

        image_hash,
        shop_name,
        bill_date,
        gst_number,
        category,
        total,
        calculated_total,
        fraud_score,
        status,
        timestamp

    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        image_hash,
        shop_name,
        bill_date,
        gst_number,
        category,
        total,
        calculated_total,
        fraud_score,
        status,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()
    conn.close()

# ==========================================================
# LOGIN SYSTEM
# ==========================================================

APP_USERNAME = st.secrets.get(
    "APP_USERNAME",
    "admin"
)

APP_PASSWORD = st.secrets.get(
    "APP_PASSWORD",
    "password123"
)

def login_screen():

    st.markdown(
        """
        <div style='text-align:center;padding:40px'>
            <h1>🧾 Deep CSC</h1>
            <h3>AI Bill Processor Premium</h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    username = st.text_input(
        "Username"
    )

    password = st.text_input(
        "Password",
        type="password"
    )

    if st.button(
        "🔐 Login",
        use_container_width=True
    ):

        if (
            username == APP_USERNAME
            and
            password == APP_PASSWORD
        ):

            st.session_state.logged_in = True
            st.rerun()

        else:

            st.error(
                "Invalid Credentials"
            )

# ==========================================================
# LOGIN CHECK
# ==========================================================

if not st.session_state.logged_in:

    login_screen()

    st.stop()

# ==========================================================
# SIDEBAR
# ==========================================================
[
    "📤 Upload & Process",
    "📠 Scanner",
    "📊 Dashboard",
    "⚙ Settings"
]
st.sidebar.title(
    "🧾 Deep CSC"
)

st.sidebar.caption(
    "Digital Seva AI Platform"
)

app_mode = st.sidebar.radio(
    "Navigation",
    [
        "📤 Upload & Process",
        "📊 Dashboard",
        "⚙ Settings"
    ]
)

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True
):

    st.session_state.logged_in = False
    st.rerun()

# ==========================================================
# GEMINI CONFIG
# ==========================================================

GEMINI_API_KEY = st.secrets.get(
    "GEMINI_API_KEY",
    ""
)

if not GEMINI_API_KEY:

    st.error(
        "Missing GEMINI_API_KEY"
    )
    st.stop()

genai.configure(
    api_key=GEMINI_API_KEY
)

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

# ==========================================================
# PART 1 COMPLETE
# ==========================================================
# ==========================================================
# PART 2
# OCR ENGINE + VALIDATION + FRAUD DETECTION
# ==========================================================

@st.cache_data(show_spinner=False)
def validate_gst(gst):

    if not gst:
        return False, ""

    gst = str(gst).upper().strip()

    gst = re.sub(
        r"[^A-Z0-9]",
        "",
        gst
    )

    pattern = (
        r"^[0-9]{2}"
        r"[A-Z]{5}"
        r"[0-9]{4}"
        r"[A-Z]{1}"
        r"[1-9A-Z]{1}"
        r"Z"
        r"[0-9A-Z]{1}$"
    )

    return bool(
        re.match(pattern, gst)
    ), gst


# ==========================================================
# EXPENSE CATEGORY DETECTOR
# ==========================================================

def detect_category(items):

    text = " ".join(
        [
            str(
                x.get("name", "")
            ).lower()
            for x in items
        ]
    )

    mapping = {

        "milk": "Dairy",
        "curd": "Dairy",
        "paneer": "Dairy",

        "medicine": "Medical",
        "tablet": "Medical",

        "pen": "Stationery",
        "paper": "Stationery",

        "diesel": "Travel",
        "petrol": "Travel",

        "electricity": "Electricity",

        "wifi": "Internet",
        "broadband": "Internet"

    }

    for key, value in mapping.items():

        if key in text:
            return value

    return "General"


# ==========================================================
# FRAUD SCORE ENGINE
# ==========================================================

def calculate_fraud_score(
    items,
    bill_total,
    calculated_total,
    gst_valid
):

    score = 0

    if not gst_valid:
        score += 25

    if len(items) == 0:
        score += 20

    diff = abs(
        calculated_total -
        bill_total
    )

    if diff > 10:
        score += 25

    if diff > 100:
        score += 20

    if bill_total == 0:
        score += 20

    return min(score, 100)


# ==========================================================
# SAFE JSON RECOVERY
# ==========================================================

def recover_json(text):

    try:
        return json.loads(text)

    except:

        start = text.find("{")
        end = text.rfind("}")

        if (
            start != -1
            and
            end != -1
        ):

            try:
                return json.loads(
                    text[start:end+1]
                )

            except:
                return None

    return None


# ==========================================================
# GEMINI OCR
# ==========================================================

def analyze_bill(image):

    prompt = """
    Analyze this bill image.

    Return ONLY valid JSON.

    {
      "shop_name":"",
      "bill_date":"",
      "gst_number":"",
      "items":[
        {
          "name":"",
          "qty":"",
          "rate":"",
          "amount":""
        }
      ],
      "total":""
    }

    Rules:

    - JSON only
    - No markdown
    - No explanation
    - Use empty string if missing
    """

    max_retries = 3

    for attempt in range(
        max_retries
    ):

        try:

            response = model.generate_content(
                [
                    prompt,
                    image
                ]
            )

            raw = (
                response.text
                .replace(
                    "```json",
                    ""
                )
                .replace(
                    "```",
                    ""
                )
                .strip()
            )

            data = recover_json(raw)

            if data:
                data["_raw"] = raw
                return data

        except Exception as e:

            if attempt < (
                max_retries - 1
            ):
                time.sleep(3)

            else:

                st.error(
                    f"OCR Error: {e}"
                )

    return None


# ==========================================================
# PROCESS BILL
# ==========================================================

def process_bill(image, file_bytes):

    data = analyze_bill(image)

    if not data:

        st.error(
            "Failed to parse bill"
        )
        return

    image_hash = generate_hash(
        file_bytes
    )

    if check_duplicate(
        image_hash
    ):

        st.warning(
            "Duplicate Bill Detected"
        )

    shop_name = str(
        data.get(
            "shop_name",
            ""
        )
    )

    bill_date = str(
        data.get(
            "bill_date",
            ""
        )
    )

    gst_number = str(
        data.get(
            "gst_number",
            ""
        )
    )

    items = data.get(
        "items",
        []
    )

    try:

        bill_total = float(
            str(
                data.get(
                    "total",
                    0
                )
            ).replace(
                ",",
                ""
            )
        )

    except:

        bill_total = 0

    df = pd.DataFrame(items)

    if (
        not df.empty
        and
        "amount" in df.columns
    ):

        df["amount"] = pd.to_numeric(
            df["amount"],
            errors="coerce"
        ).fillna(0)

        calculated_total = float(
            df["amount"].sum()
        )

    else:

        calculated_total = 0

    gst_valid, gst_clean = (
        validate_gst(
            gst_number
        )
    )

    category = detect_category(
        items
    )

    fraud_score = (
        calculate_fraud_score(
            items,
            bill_total,
            calculated_total,
            gst_valid
        )
    )

    status = (
        "Matched"
        if abs(
            calculated_total -
            bill_total
        ) < 1
        else "Mismatch"
    )

    st.subheader(
        "📋 Extracted Bill"
    )

    st.write(
        f"🏪 {shop_name}"
    )

    st.write(
        f"📅 {bill_date}"
    )

    if gst_valid:

        st.success(
            f"GST Valid: {gst_clean}"
        )

    else:

        st.warning(
            f"GST Invalid: {gst_number}"
        )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Bill Total",
        f"₹{bill_total:,.2f}"
    )

    c2.metric(
        "Calculated",
        f"₹{calculated_total:,.2f}"
    )

    c3.metric(
        "Fraud Score",
        f"{fraud_score}%"
    )

    if not df.empty:

        st.dataframe(
            df,
            use_container_width=True
        )

    with st.expander(
        "🔍 Raw OCR Response"
    ):

        st.code(
            data.get(
                "_raw",
                ""
            )
        )

    save_bill(
        image_hash,
        shop_name,
        bill_date,
        gst_clean,
        category,
        bill_total,
        calculated_total,
        fraud_score,
        status
    )
# ==========================================================
# PART 3
# UPLOAD UI + CAMERA + DASHBOARD
# ==========================================================

if app_mode == "📤 Upload & Process":

    st.title("🧾 Deep CSC AI Bill Processor")

    tab1, tab2 = st.tabs(
        [
            "📤 Upload Bills",
            "📸 Camera Capture"
        ]
    )

    # =====================================
    # FILE UPLOAD
    # =====================================

    with tab1:

        uploaded_files = st.file_uploader(
            "Upload Bill Images",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True
        )

        if uploaded_files:

            st.success(
                f"{len(uploaded_files)} file(s) loaded"
            )

            for file in uploaded_files:

                st.markdown("---")

                image = Image.open(file)

                st.image(
                    image,
                    caption=file.name,
                    width=350
                )

                if st.button(
                    f"Analyze {file.name}",
                    key=file.name
                ):

                    process_bill(
                        image,
                        file.getvalue()
                    )

    # =====================================
    # CAMERA
    # =====================================

    with tab2:

        camera = st.camera_input(
            "Capture Bill"
        )

        if camera:

            image = Image.open(camera)

            st.image(
                image,
                caption="Captured Bill"
            )

            if st.button(
                "Analyze Captured Bill"
            ):

                process_bill(
                    image,
                    camera.getvalue()
                )

# ==========================================================
# DASHBOARD
# ==========================================================

elif app_mode == "📊 Dashboard":

    st.title(
        "📊 Financial Dashboard"
    )

    conn = sqlite3.connect(
        "bills.db"
    )

    df = pd.read_sql_query(
        "SELECT * FROM bills",
        conn
    )

    conn.close()

    if df.empty:

        st.warning(
            "No bills processed yet"
        )

    else:

        total_bills = len(df)

        total_amount = (
            df["total"]
            .fillna(0)
            .sum()
        )

        avg_bill = (
            total_amount
            / total_bills
        )

        fraud_avg = (
            df["fraud_score"]
            .fillna(0)
            .mean()
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Bills",
            total_bills
        )

        c2.metric(
            "Amount",
            f"₹{total_amount:,.2f}"
        )

        c3.metric(
            "Average",
            f"₹{avg_bill:,.2f}"
        )

        c4.metric(
            "Fraud Risk",
            f"{fraud_avg:.1f}%"
        )

        st.markdown("---")

        st.subheader(
            "Vendor Analysis"
        )

        vendor_df = (
            df.groupby(
                "shop_name"
            )["total"]
            .sum()
            .reset_index()
            .sort_values(
                "total",
                ascending=False
            )
        )

        st.bar_chart(
            vendor_df.set_index(
                "shop_name"
            )
        )

        st.subheader(
            "Category Analysis"
        )

        cat_df = (
            df.groupby(
                "category"
            )["total"]
            .sum()
            .reset_index()
        )

        st.dataframe(
            cat_df,
            use_container_width=True
        )

        st.subheader(
            "Bill History"
        )

        search = st.text_input(
            "Search Vendor"
        )

        if search:

            df = df[
                df["shop_name"]
                .str.contains(
                    search,
                    case=False,
                    na=False
                )
            ]

        st.dataframe(
            df,
            use_container_width=True
        )

# ==========================================================
# SETTINGS
# ==========================================================
elif app_mode == "📠 Scanner":

    st.title("📠 Brother Scanner")

    dpi = st.selectbox(
        "DPI",
        [150, 300, 600],
        index=1
    )

    if st.button("🚀 Scan Bill"):

        with st.spinner("Scanning..."):

            file = scan_document(dpi)

            if file:

                image = Image.open(file)

                st.image(image)

                with open(file, "rb") as f:

                    process_bill(
                        image,
                        f.read()
                    )

            else:

                st.error(
                    "Scanner not detected"
                )
elif app_mode == "⚙ Settings":

    st.title("⚙ Settings")

    st.info(
        f"Scanner Available: {IS_LOCAL}"
    )

    st.code(
        r"C:\Program Files\NAPS2\NAPS2.Console.exe"
    )

    st.success(
        "Enterprise Edition Active"
    )
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet
)

def generate_pdf(
    shop_name,
    bill_date,
    gst_number,
    bill_total,
    fraud_score
):

    pdf_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    )

    doc = SimpleDocTemplate(
        pdf_file.name
    )

    styles = getSampleStyleSheet()

    elements = [

        Paragraph(
            "Deep CSC Bill Report",
            styles["Title"]
        ),

        Spacer(1, 20),

        Paragraph(
            f"Vendor : {shop_name}",
            styles["Normal"]
        ),

        Paragraph(
            f"Date : {bill_date}",
            styles["Normal"]
        ),

        Paragraph(
            f"GST : {gst_number}",
            styles["Normal"]
        ),

        Paragraph(
            f"Total : ₹{bill_total}",
            styles["Normal"]
        ),

        Paragraph(
            f"Fraud Score : {fraud_score}%",
            styles["Normal"]
        )
    ]

    doc.build(elements)

    return pdf_file.name

pdf_path = generate_pdf(
    shop_name,
    bill_date,
    gst_clean,
    bill_total,
    fraud_score
)

with open(pdf_path, "rb") as f:

    st.download_button(
        "📄 Download PDF",
        f.read(),
        file_name="bill_report.pdf",
        mime="application/pdf"
    )

excel = BytesIO()

df.to_excel(
    excel,
    index=False
)

st.download_button(
    "📊 Download Excel",
    excel.getvalue(),
    file_name="bill_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
msg = (
    f"Vendor: {shop_name}\n"
    f"Date: {bill_date}\n"
    f"Total: ₹{bill_total}\n"
    f"Fraud Score: {fraud_score}%"
)

wa_url = (
    "https://wa.me/?text="
    +
    urllib.parse.quote(msg)
)

st.link_button(
    "📱 Share WhatsApp",
    wa_url
)
