import streamlit as st
import google.generativeai as genai
from PIL import Image
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
from datetime import datetime
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# ==========================================================
# PAGE CONFIG & STATE
# ==========================================================
st.set_page_config(page_title="Deep CSC AI Premium", layout="wide")
if "logged_in" not in st.session_state: st.session_state.logged_in = False

# ==========================================================
# HELPER FUNCTIONS (OCR, DB, VALIDATION)
# ==========================================================
def init_db():
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS bills 
                  (id INTEGER PRIMARY KEY, image_hash TEXT, shop_name TEXT, total REAL, fraud_score REAL, status TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

def validate_gst(gst):
    if not gst: return False, "N/A"
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    return bool(re.match(pattern, str(gst).upper())), gst

def analyze_bill(image):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = "Extract shop_name, bill_date, gst_number, total, items(name, qty, rate, amount) in JSON."
    response = model.generate_content([prompt, image])
    try: return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except: return None

# ==========================================================
# EXPORT SECTION
# ==========================================================
def export_section(shop_name, bill_date, total, fraud, df):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("📊 Download Excel", df.to_csv(index=False), "bill.csv", "text/csv")
    with c3:
        wa_url = f"https://wa.me/?text=Bill Details: {shop_name}, Total: {total}, Fraud Score: {fraud}%"
        st.link_button("📱 Share WhatsApp", wa_url)

# ==========================================================
# LOGIN SCREEN
# ==========================================================
if not st.session_state.logged_in:
    st.title("🔐 Login to Deep CSC")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if user == "admin" and pwd == "password123":
            st.session_state.logged_in = True
            st.rerun()
        else: st.error("Invalid")
    st.stop()

# ==========================================================
# MAIN APP
# ==========================================================
st.sidebar.title("🧾 Deep CSC Platform")
mode = st.sidebar.radio("Navigation", ["📤 Process", "📊 Dashboard", "⚙ Settings"])

if mode == "📤 Process":
    st.title("Upload/Capture Bill")
    uploaded_file = st.file_uploader("Upload", type=["jpg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        if st.button("Analyze"):
            data = analyze_bill(image)
            if data:
                st.write(f"Shop: {data.get('shop_name')}")
                st.metric("Total", data.get("total"))
                df = pd.DataFrame(data.get("items", []))
                st.dataframe(df)
                export_section(data.get('shop_name'), "", data.get('total'), 0, df)
            else: st.error("Parsing failed")

elif mode == "📊 Dashboard":
    st.title("Financial Dashboard")
    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    st.dataframe(df)
    conn.close()

elif mode == "⚙ Settings":
    st.info("System Ready. Enterprise Edition Active.")
