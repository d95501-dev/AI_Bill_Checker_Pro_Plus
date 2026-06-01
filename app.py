import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
import sqlite3
import json
import re
import time
import tempfile
import urllib.parse

from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet
)

# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="Deep CSC AI Bill Processor",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# PREMIUM CSS
# ==========================================

st.markdown("""
<style>

.main {
    background:#f8fafc;
}

.block-container{
    padding-top:1rem;
}

.deep-header{
    background: linear-gradient(
        135deg,
        #0f172a,
        #1e293b
    );

    padding:30px;
    border-radius:20px;
    margin-bottom:20px;
}

.deep-title{
    font-size:34px;
    font-weight:900;
    color:white;
}

.deep-sub{
    color:#cbd5e1;
    font-size:14px;
}

.stButton>button{
    width:100%;
    border-radius:12px;
    font-weight:700;
}

div[data-testid="stMetric"]{
    background:white;
    border-radius:18px;
    padding:18px;
    box-shadow:
    0 2px 10px rgba(0,0,0,.05);
}

.sidebar-brand{
    background:#0f172a;
    padding:20px;
    border-radius:16px;
    text-align:center;
}

.sidebar-title{
    color:#38bdf8;
    font-size:28px;
    font-weight:900;
}

.sidebar-sub{
    color:#f472b6;
    font-size:13px;
}

</style>
""", unsafe_allow_html=True)

# ==========================================
# DATABASE
# ==========================================

def init_db():

    conn = sqlite3.connect("bills.db")

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bills(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        shop_name TEXT,
        bill_date TEXT,
        gst_number TEXT,

        total REAL,
        calculated_total REAL,

        status TEXT,

        timestamp TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ==========================================
# INSERT BILL
# ==========================================

def insert_bill(
    shop,
    bill_date,
    gst,
    total,
    calc_total,
    status
):

    conn = sqlite3.connect("bills.db")

    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM bills
        WHERE shop_name=?
        AND bill_date=?
        AND total=?
        """,
        (
            shop,
            bill_date,
            total
        )
    )

    existing = cur.fetchone()

    if existing:
        conn.close()

        return (
            False,
            "Duplicate bill detected"
        )

    cur.execute(
        """
        INSERT INTO bills(

            shop_name,
            bill_date,
            gst_number,

            total,
            calculated_total,

            status,
            timestamp

        )

        VALUES(
            ?,?,?,?,?,?,?
        )
        """,
        (
            shop,
            bill_date,
            gst,

            total,
            calc_total,

            status,

            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    conn.commit()
    conn.close()

    return (
        True,
        "Saved"
    )

# ==========================================
# GST VALIDATOR
# ==========================================

def validate_gst(gst):

    gst_regex = (
        r'^[0-9]{2}'
        r'[A-Z]{5}'
        r'[0-9]{4}'
        r'[A-Z]{1}'
        r'[1-9A-Z]{1}'
        r'Z'
        r'[0-9A-Z]{1}$'
    )

    gst = re.sub(
        r'[^A-Z0-9]',
        '',
        str(gst).upper()
    )

    return bool(
        re.match(
            gst_regex,
            gst
        )
    )

# ==========================================
# LOGIN SYSTEM
# ==========================================

APP_USERNAME = st.secrets.get(
    "APP_USERNAME",
    "admin"
)

APP_PASSWORD = st.secrets.get(
    "APP_PASSWORD",
    "password123"
)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.markdown("""
    <div class="deep-header">

    <div class="deep-title">
    Deep CSC
    </div>

    <div class="deep-sub">
    Authorized Digital Seva Portal
    </div>

    </div>
    """, unsafe_allow_html=True)

    st.title("🔐 Login")

    username = st.text_input(
        "Username"
    )

    password = st.text_input(
        "Password",
        type="password"
    )

    if st.button(
        "Login",
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

    st.stop()

# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.markdown("""
<div class="sidebar-brand">

<div class="sidebar-title">
Deep CSC
</div>

<div class="sidebar-sub">
AI BILL PROCESSOR
</div>

</div>
""", unsafe_allow_html=True)

st.sidebar.write("👤 Operator")

app_mode = st.sidebar.selectbox(
    "Navigation",
    [
        "📤 Upload & Process",
        "📊 Dashboard & History"
    ]
)

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True
):

    st.session_state.logged_in = False

    st.rerun()

# ==========================================
# GEMINI SETUP
# ==========================================

API_KEY = st.secrets.get(
    "GEMINI_API_KEY",
    ""
)

if not API_KEY:

    st.error(
        "GEMINI_API_KEY missing"
    )

    st.stop()

genai.configure(
    api_key=API_KEY
)

try:

    model = genai.GenerativeModel(
        "gemini-2.5-flash"
    )

except Exception as e:

    st.error(
        f"Gemini Error : {e}"
    )

    st.stop()

# ==========================================
# MODULE 1
# UPLOAD + SCANNER + OCR
# ==========================================

if app_mode == "📤 Upload & Process":

    st.markdown("""
    <div class="deep-header">
        <div class="deep-title">
            🧾 AI Multi Bill Processor
        </div>

        <div class="deep-sub">
            Gemini Vision OCR + Audit Engine
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ==================================
    # INPUT SOURCE
    # ==================================

    st.subheader("📥 Input Source")

    source = st.radio(
        "Choose Source",
        [
            "📂 Upload Files",
            "📷 Camera Scanner"
        ],
        horizontal=True
    )

    uploaded_files = []

    # ----------------------------------
    # FILE UPLOAD
    # ----------------------------------

    if source == "📂 Upload Files":

        files = st.file_uploader(
            "Upload Bill Images",
            type=[
                "jpg",
                "jpeg",
                "png"
            ],
            accept_multiple_files=True
        )

        if files:
            uploaded_files = files

    # ----------------------------------
    # CAMERA SCANNER
    # ----------------------------------

    if source == "📷 Camera Scanner":

        st.info(
            "Capture bill directly using camera"
        )

        camera_file = st.camera_input(
            "Scanner Feed"
        )

        if camera_file:
            uploaded_files = [camera_file]

    # ==================================
    # PROCESS FILES
    # ==================================

    if uploaded_files:

        st.success(
            f"{len(uploaded_files)} file(s) ready"
        )

        for idx, file in enumerate(
            uploaded_files
        ):

            st.markdown("---")

            st.subheader(
                f"📄 Bill #{idx+1}"
            )

            image = Image.open(file)

            left, right = st.columns(
                [1, 2]
            )

            with left:

                st.image(
                    image,
                    use_container_width=True
                )

            with right:

                if st.button(
                    f"⚡ Analyze Bill {idx+1}",
                    key=f"ocr_{idx}"
                ):

                    with st.spinner(
                        "Gemini OCR Processing..."
                    ):

                        prompt = """
Analyze this bill.

Return ONLY valid JSON.

Format:

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
"""

                        try:

                            response = (
                                model.generate_content(
                                    [
                                        prompt,
                                        image
                                    ]
                                )
                            )

                            raw_text = (
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

                            match = re.search(
                                r"\{.*\}",
                                raw_text,
                                re.DOTALL
                            )

                            if match:
                                raw_text = (
                                    match.group()
                                )

                            data = json.loads(
                                raw_text
                            )

                        except Exception as e:

                            st.error(
                                f"OCR Failed : {e}"
                            )

                            continue

                        # ===================
                        # EXTRACT DATA
                        # ===================

                        shop_name = data.get(
                            "shop_name",
                            "Unknown"
                        )

                        bill_date = data.get(
                            "bill_date",
                            datetime.now().strftime(
                                "%Y-%m-%d"
                            )
                        )

                        gst_number = data.get(
                            "gst_number",
                            ""
                        )

                        items = data.get(
                            "items",
                            []
                        )

                        st.success(
                            "OCR Completed"
                        )

                        st.markdown(
                            f"### 🏪 {shop_name}"
                        )

                        col1, col2 = st.columns(
                            2
                        )

                        with col1:
                            st.write(
                                f"📅 {bill_date}"
                            )

                        with col2:

                            if gst_number:

                                if validate_gst(
                                    gst_number
                                ):

                                    st.success(
                                        f"GST Valid : {gst_number}"
                                    )

                                else:

                                    st.warning(
                                        f"GST Invalid : {gst_number}"
                                    )

                        # ===================
                        # ITEMS TABLE
                        # ===================

                        if items:

                            df = pd.DataFrame(
                                items
                            )

                            st.dataframe(
                                df,
                                use_container_width=True
                            )

                            if (
                                "amount"
                                in df.columns
                            ):

                                df["amount"] = (
                                    pd.to_numeric(
                                        df["amount"],
                                        errors="coerce"
                                    )
                                    .fillna(0)
                                )

                                calculated_total = (
                                    float(
                                        df["amount"]
                                        .sum()
                                    )
                                )

                            else:

                                calculated_total = 0

                        else:

                            st.warning(
                                "No line items found"
                            )

                            calculated_total = 0

                        # ===================
                        # TOTAL
                        # ===================

                        try:

                            bill_total = float(
                                str(
                                    data.get(
                                        "total",
                                        0
                                    )
                                )
                                .replace(
                                    ",",
                                    ""
                                )
                            )

                        except:

                            bill_total = 0

                        difference = abs(
                            calculated_total
                            - bill_total
                        )

                        status = (
                            "Matched"
                            if difference < 1
                            else "Mismatch"
                        )

                        # ===================
                        # AUDIT
                        # ===================

                        st.subheader(
                            "📊 Audit Engine"
                        )

                        a1, a2 = st.columns(2)

                        with a1:

                            st.metric(
                                "Calculated",
                                f"₹{calculated_total:,.2f}"
                            )

                        with a2:

                            st.metric(
                                "Bill Total",
                                f"₹{bill_total:,.2f}"
                            )

                        if status == "Matched":

                            st.success(
                                "✅ Arithmetic Verified"
                            )

                        else:

                            st.error(
                                f"❌ Difference ₹{difference:,.2f}"
                            )

                        # ===================
                        # DATABASE SAVE
                        # ===================

                        saved, msg = (
                            insert_bill(
                                shop_name,
                                bill_date,
                                gst_number,
                                bill_total,
                                calculated_total,
                                status
                            )
                        )

                        if saved:

                            st.toast(
                                "Saved to DB"
                            )

                        else:

                            st.warning(
                                msg
                            )

                        # ===================
                        # SESSION STORAGE
                        # ===================

                        st.session_state[
                            "latest_bill"
                        ] = {
                            "shop_name":
                                shop_name,
                            "bill_date":
                                bill_date,
                            "gst":
                                gst_number,
                            "items":
                                items,
                            "total":
                                bill_total,
                            "status":
                                status
                        }
# ==========================================
# MODULE 2
# DASHBOARD + EXPORT + HISTORY
# ==========================================

elif app_mode == "📊 Dashboard & History":

    st.markdown("""
    <div class="deep-header">
        <div class="deep-title">
            📊 Financial Dashboard
        </div>

        <div class="deep-sub">
            Ledger Analytics & Audit History
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ==========================================
    # LOAD DATA
    # ==========================================

    conn = sqlite3.connect("bills.db")

    df = pd.read_sql_query(
        "SELECT * FROM bills ORDER BY id DESC",
        conn
    )

    conn.close()

    if df.empty:

        st.info(
            "No records found yet. Process bills first."
        )

        st.stop()

    # ==========================================
    # METRICS
    # ==========================================

    total_spent = float(df["total"].sum())
    total_bills = len(df)
    mismatch = len(df[df["status"] == "Mismatch"])

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "💰 Total Value",
            f"₹{total_spent:,.2f}"
        )

    with c2:
        st.metric(
            "📄 Bills",
            total_bills
        )

    with c3:

        st.metric(
            "⚠️ Mismatches",
            mismatch
        )

    st.markdown("---")

    # ==========================================
    # SEARCH FILTER
    # ==========================================

    search = st.text_input(
        "🔍 Search Vendor"
    )

    filtered = df.copy()

    if search:

        filtered = df[
            df["shop_name"]
            .str.contains(
                search,
                case=False,
                na=False
            )
        ]

    # ==========================================
    # CHART DATA
    # ==========================================

    st.subheader("📊 Vendor Analytics")

    chart = (
        filtered.groupby("shop_name")["total"]
        .sum()
        .reset_index()
    )

    st.bar_chart(
        chart.set_index("shop_name")
    )

    # ==========================================
    # DATA TABLE
    # ==========================================

    st.subheader("📋 Ledger Records")

    st.dataframe(
        filtered,
        use_container_width=True
    )

    # ==========================================
    # EXPORT EXCEL
    # ==========================================

    excel_buffer = BytesIO()

    with pd.ExcelWriter(
        excel_buffer,
        engine="openpyxl"
    ) as writer:

        filtered.to_excel(
            writer,
            index=False,
            sheet_name="Bills"
        )

    st.download_button(
        "📥 Download Excel",
        data=excel_buffer.getvalue(),
        file_name="bills.xlsx",
        mime="application/vnd.ms-excel"
    )

    # ==========================================
    # PDF EXPORT (LATEST BILL)
    # ==========================================

    if "latest_bill" in st.session_state:

        bill = st.session_state["latest_bill"]

        pdf_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        )

        doc = SimpleDocTemplate(pdf_file.name)

        styles = getSampleStyleSheet()

        content = []

        content.append(
            Paragraph(
                "AI BILL REPORT",
                styles["Title"]
            )
        )

        content.append(Spacer(1, 10))

        content.append(
            Paragraph(
                f"Shop: {bill['shop_name']}",
                styles["Normal"]
            )
        )

        content.append(
            Paragraph(
                f"Date: {bill['bill_date']}",
                styles["Normal"]
            )
        )

        content.append(
            Paragraph(
                f"Total: ₹{bill['total']}",
                styles["Heading3"]
            )
        )

        content.append(
            Paragraph(
                f"Status: {bill['status']}",
                styles["Normal"]
            )
        )

        doc.build(content)

        with open(pdf_file.name, "rb") as f:

            st.download_button(
                "📄 Download PDF Report",
                f,
                file_name="bill_report.pdf"
            )

    # ==========================================
    # WHATSAPP SHARE
    # ==========================================

    if "latest_bill" in st.session_state:

        bill = st.session_state["latest_bill"]

        msg = (
            f"Bill Report\n"
            f"Shop: {bill['shop_name']}\n"
            f"Total: ₹{bill['total']}\n"
            f"Status: {bill['status']}"
        )

        url = (
            "https://wa.me/?text="
            + urllib.parse.quote(msg)
        )

        st.link_button(
            "📱 Share on WhatsApp",
            url
        )

    # ==========================================
    # MASTER EXPORT
    # ==========================================

    st.markdown("---")

    master_buffer = BytesIO()

    with pd.ExcelWriter(
        master_buffer,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="MASTER_DB"
        )

    st.download_button(
        "📦 Download Full Database",
        data=master_buffer.getvalue(),
        file_name="master_db.xlsx",
        mime="application/vnd.ms-excel"
    )

    # ==========================================
    # CLEAN ANALYTICS
    # ==========================================

    st.subheader("📈 Quick Insights")

    col1, col2 = st.columns(2)

    with col1:

        st.bar_chart(
            df.groupby("status")["total"].count()
        )

    with col2:

        st.bar_chart(
            df.groupby("shop_name")["total"].sum().head(5)
        )
