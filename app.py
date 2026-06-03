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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

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
# ENV & DB SETUP
# ==========================================================
IS_LOCAL = (platform.system() == "Windows" and os.path.exists(r"C:\Program Files\NAPS2\NAPS2.Console.exe"))
NAPS2_PATH = r"C:\Program Files\NAPS2\NAPS2.Console.exe"

def init_db():
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT, image_hash TEXT, shop_name TEXT, 
        bill_date TEXT, gst_number TEXT, category TEXT, total REAL, 
        calculated_total REAL, fraud_score REAL, status TEXT, timestamp TEXT)""")
    conn.commit()
    conn.close()

init_db()

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def generate_hash(file_bytes): return hashlib.md5(file_bytes).hexdigest()

def check_duplicate(image_hash):
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute("SELECT id FROM bills WHERE image_hash = ?", (image_hash,))
    result = cur.fetchone()
    conn.close()
    return result is not None

def save_bill(image_hash, shop_name, bill_date, gst_number, category, total, calculated_total, fraud_score, status):
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute("""INSERT INTO bills (image_hash, shop_name, bill_date, gst_number, category, total, 
                   calculated_total, fraud_score, status, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (image_hash, shop_name, bill_date, gst_number, category, total, calculated_total, 
                 fraud_score, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ==========================================================
# PDF & EXPORT ENGINE
# ==========================================================
def generate_pdf(shop_name, bill_date, gst_number, bill_total, fraud_score):
    pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(pdf_file.name)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Deep CSC Bill Report", styles["Title"]), Spacer(1, 20),
                Paragraph(f"Vendor : {shop_name}", styles["Normal"]),
                Paragraph(f"Date : {bill_date}", styles["Normal"]),
                Paragraph(f"GST : {gst_number}", styles["Normal"]),
                Paragraph(f"Total : ₹{bill_total}", styles["Normal"]),
                Paragraph(f"Fraud Score : {fraud_score}%", styles["Normal"])]
    doc.build(elements)
    return pdf_file.name

def export_section(shop_name, bill_date, gst_clean, bill_total, fraud_score, df):
    pdf_path = generate_pdf(shop_name, bill_date, gst_clean, bill_total, fraud_score)
    c1, c2, c3 = st.columns(3)
    with c1:
        with open(pdf_path, "rb") as f:
            st.download_button("📄 Download PDF", f.read(), file_name=f"{shop_name}.pdf", mime="application/pdf")
    with c2:
        excel = BytesIO()
        if not df.empty: df.to_excel(excel, index=False)
        st.download_button("📊 Download Excel", excel.getvalue(), file_name=f"{shop_name}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c3:
        msg = f"Vendor: {shop_name}\nDate: {bill_date}\nTotal: ₹{bill_total}\nFraud Score: {fraud_score}%"
        wa_url = "https://wa.me/?text=" + urllib.parse.quote(msg)
        st.link_button("📱 Share WhatsApp", wa_url)

# ==========================================================
# MAIN LOGIC (Simplified for brevity, integrate your existing OCR/Process functions here)
# ==========================================================
# [Insert your existing validate_gst, detect_category, calculate_fraud_score, analyze_bill, process_bill functions here]

# ==========================================================
# SIDEBAR & APP FLOW
# ==========================================================
if not st.session_state.get("logged_in", False):
    # (Insert your login screen here)
    st.stop()

st.sidebar.title("🧾 Deep CSC")
app_mode = st.sidebar.radio("Navigation", ["📤 Upload & Process", "📠 Scanner", "📊 Dashboard", "⚙ Settings"])

if app_mode == "📤 Upload & Process":
    # (Your upload code)
    pass
elif app_mode == "📊 Dashboard":
    # (Your dashboard code)
    pass
elif app_mode == "📠 Scanner":
    # (Your scanner code)
    pass
elif app_mode == "⚙ Settings":
    st.title("⚙ Settings")
    st.info(f"Scanner Available: {IS_LOCAL}")
