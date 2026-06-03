import streamlit as st
import google.generativeai as genai
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
import subprocess
from PIL import Image
from datetime import datetime
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# ==========================================================
# CONFIG & SETUP
# ==========================================================
st.set_page_config(page_title="Deep CSC AI Premium", layout="wide")
if "logged_in" not in st.session_state: st.session_state.logged_in = True # Default True for testing

# Gemini Setup
genai.configure(api_key=st.secrets.get("GEMINI_API_KEY", "YOUR_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# ==========================================================
# CORE ENGINE (OCR, SCANNER, VALIDATION)
# ==========================================================
def scan_document():
    if not os.path.exists(r"C:\Program Files\NAPS2\NAPS2.Console.exe"): return None
    output = "scan.jpg"
    cmd = [r"C:\Program Files\NAPS2\NAPS2.Console.exe", "--driver", "wia", "-o", output, "-f"]
    subprocess.run(cmd, capture_output=True)
    return output if os.path.exists(output) else None

def validate_gst(gst):
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    return bool(re.match(pattern, str(gst).upper())), gst

def analyze_bill(image):
    prompt = "Extract shop_name, bill_date, gst_number, total, and items(name, qty, rate, amount) as JSON."
    try:
        response = model.generate_content([prompt, image])
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except: return None

# ==========================================================
# PDF & EXPORT ENGINE
# ==========================================================
def export_section(shop_name, bill_date, gst, total, fraud, df):
    c1, c2, c3 = st.columns(3)
    # Excel Export
    excel = BytesIO()
    df.to_excel(excel, index=False)
    c1.download_button("📊 Download Excel", excel.getvalue(), f"{shop_name}.xlsx")
    # WhatsApp Share
    msg = f"Bill: {shop_name}, Total: ₹{total}, Fraud Score: {fraud}%"
    c3.link_button("📱 Share WhatsApp", "https://wa.me/?text=" + urllib.parse.quote(msg))

# ==========================================================
# MAIN INTERFACE
# ==========================================================
st.sidebar.title("🧾 Deep CSC AI")
app_mode = st.sidebar.radio("Navigation", ["📤 Upload & Process", "📠 Scanner", "📊 Dashboard"])

if app_mode == "📤 Upload & Process":
    st.title("📤 Process Bill")
    uploaded = st.file_uploader("Upload Bill", type=["jpg", "png"])
    if uploaded:
        image = Image.open(uploaded)
        st.image(image, width=300)
        if st.button("Analyze"):
            data = analyze_bill(image)
            if data:
                st.json(data)
                df = pd.DataFrame(data.get("items", []))
                export_section(data.get("shop_name"), "", "", data.get("total"), 0, df)
            else: st.error("Parsing failed")

elif app_mode == "📠 Scanner":
    st.title("📠 Local Scanner")
    if st.button("Scan Now"):
        with st.spinner("Scanning..."):
            path = scan_document()
            if path: st.image(path)
            else: st.error("Scanner not found")

elif app_mode == "📊 Dashboard":
    st.title("📊 Financial Data")
    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    st.dataframe(df)
    conn.close()
