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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# CONFIG
# ==========================
st.set_page_config(
    page_title="Deep CSC AI Bill Processor",
    page_icon="🧾",
    layout="wide"
)

# ==========================
# GEMINI
# ==========================
API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not API_KEY:
    st.error("GEMINI_API_KEY missing")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================
# DATABASE
# ==========================
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

def insert_bill(shop, date, gst, total, calc_total, status):
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()

    cur.execute("SELECT id FROM bills WHERE shop_name=? AND bill_date=? AND total=?",
                (shop, date, total))
    if cur.fetchone():
        return False

    cur.execute("""
        INSERT INTO bills(shop_name,bill_date,gst_number,total,calculated_total,status,timestamp)
        VALUES(?,?,?,?,?,?,?)
    """, (shop, date, gst, total, calc_total, status,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()
    return True

# ==========================
# LOGIN (simple)
# ==========================
if "login" not in st.session_state:
    st.session_state.login = False

if not st.session_state.login:
    st.title("🔐 Deep CSC Login")
    u = st.text_input("User")
    p = st.text_input("Pass", type="password")

    if st.button("Login"):
        if u == st.secrets.get("APP_USERNAME","admin") and p == st.secrets.get("APP_PASSWORD","123"):
            st.session_state.login = True
            st.rerun()
        else:
            st.error("Wrong credentials")
    st.stop()

# ==========================
# UI
# ==========================
st.title("🧾 AI Bill Processor PRO")

page = st.sidebar.selectbox("Menu", ["Scan & Process", "Dashboard"])

# ==========================
# SCANNER MODULE (FIXED)
# ==========================
def scanner_ui():
    st.subheader("📷 Smart Scanner System")

    mode = st.radio("Input Mode", ["Camera Scanner", "File Upload", "Printer Scan (Simulated)"], horizontal=True)

    file = None

    if mode == "Camera Scanner":
        file = st.camera_input("Scan Bill")

    elif mode == "File Upload":
        file = st.file_uploader("Upload Bill", type=["jpg","png","jpeg"])

    elif mode == "Printer Scan (Simulated)":
        st.warning("⚠ Real printer-scanner requires TWAIN/WIA driver")
        file = st.file_uploader("Select scanned file (from printer scanner folder)", type=["jpg","png","jpeg"])

    return file

# ==========================
# OCR FUNCTION
# ==========================
def run_ocr(image):
    prompt = """
Extract bill in JSON:
{
 shop_name:"",
 bill_date:"",
 gst_number:"",
 items:[{"name":"","qty":"","rate":"","amount":""}],
 total:""
}
"""

    res = model.generate_content([prompt, image])
    txt = res.text.replace("```json","").replace("```","")

    match = re.search(r"\{.*\}", txt, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}

# ==========================
# SCAN PAGE
# ==========================
if page == "Scan & Process":

    file = scanner_ui()

    if file:

        img = Image.open(file)
        st.image(img, use_container_width=True)

        if st.button("🚀 Process Bill"):

            with st.spinner("AI Processing..."):
                data = run_ocr(img)

            shop = data.get("shop_name","Unknown")
            date = data.get("bill_date", datetime.now().strftime("%Y-%m-%d"))
            gst = data.get("gst_number","")
            items = data.get("items",[])
            total = float(data.get("total",0))

            df = pd.DataFrame(items)

            if "amount" in df.columns:
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
                calc = df["amount"].sum()
            else:
                calc = 0

            status = "Matched" if abs(calc-total)<1 else "Mismatch"

            st.success(f"{shop}")

            st.metric("Total", total)
            st.metric("Calculated", calc)

            st.write(df)

            insert_bill(shop,date,gst,total,calc,status)

            st.success("Saved to DB")

            # PDF
            pdf = tempfile.NamedTemporaryFile(delete=False,suffix=".pdf")
            doc = SimpleDocTemplate(pdf.name)
            styles = getSampleStyleSheet()

            doc.build([
                Paragraph("AI BILL REPORT", styles["Title"]),
                Paragraph(shop, styles["Normal"]),
                Paragraph(str(total), styles["Heading3"])
            ])

            st.download_button("📄 PDF", open(pdf.name,"rb"), file_name="bill.pdf")

# ==========================
# DASHBOARD
# ==========================
elif page == "Dashboard":

    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    conn.close()

    st.metric("Total Bills", len(df))

    st.bar_chart(df.groupby("status")["total"].count())

    st.dataframe(df)
