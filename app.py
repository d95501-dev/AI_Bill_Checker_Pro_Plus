import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import urllib.parse
import tempfile
import json
import re
import sqlite3
from datetime import datetime
import time

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(
    page_title="AI Bill Checker Pro",
    page_icon="🧾",
    layout="wide"
)

# -------------------------
# DATABASE SETUP
# -------------------------
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT,
            bill_date TEXT,
            gst_number TEXT,
            total REAL,
            calculated_total REAL,
            status TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def insert_bill(shop, date, gst, total, calc_total, status):
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM bills WHERE shop_name=? AND bill_date=? AND total=?", 
        (shop, date, total)
    )
    duplicate = cursor.fetchone()
    
    if duplicate:
        conn.close()
        return False, "Duplicate detected in Database!"
        
    cursor.execute('''
        INSERT INTO bills (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "Successfully saved to DB"

# -------------------------
# LOGIN SYSTEM
# -------------------------
USERNAME = st.secrets.get("APP_USERNAME", "admin")
PASSWORD = st.secrets.get("APP_PASSWORD", "password123")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 AI Bill Checker Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username == USERNAME and password == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password")
    st.stop()

# -------------------------
# SIDEBAR NAVIGATION
# -------------------------
st.sidebar.success(f"Logged In as: {USERNAME}")
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.rerun()

# -------------------------
# GEMINI SETUP
# -------------------------
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    st.error("Please configure GEMINI_API_KEY in your Streamlit secrets.")
    st.stop()

genai.configure(api_key=api_key)
try:
    model = genai.GenerativeModel("gemini-2.5-flash")
except Exception as e:
    st.error(f"Model Error: {e}")
    st.stop()

# -------------------------
# HELPER VALIDATIONS
# -------------------------
def validate_gst(gst_str):
    gst_regex = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    clean_gst = re.sub(r'[^A-Z0-9]', '', gst_str.upper())
    if re.match(gst_regex, clean_gst):
        return True, clean_gst
    return False, clean_gst

# -------------------------
# MODULE 1: UPLOAD & PROCESS
# -------------------------
if app_mode == "📤 Upload & Process":
    st.title("🧾 AI Multi-Bill OCR Processor")
    
    uploaded_files = st.file_uploader(
        "Upload Bill Images (Multiple Allowed)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            st.markdown(f"---")
            st.subheader(f"📄 Processing Item [{idx+1}]: {file.name}")
            
            image = Image.open(file)
            col_img, col_act = st.columns([1, 2])
            
            with col_img:
                st.image(image, caption=file.name, use_container_width=True)
                
            with col_act:
                if st.button(f"🔍 Analyze {file.name}", key=f"btn_{idx}"):
                    with st.spinner("Gemini AI is parsing structural data..."):
                        prompt = """
                        Analyze this bill image carefully.
                        Extract:
                        - shop_name
                        - bill_date
                        - gst_number
                        - items
                        - total

                        Return ONLY valid JSON format mapping the structure below. Do not output anything except pure JSON code block.
                        {
                          "shop_name":"",
                          "bill_date":"",
                          "gst_number":"",
                          "items":[
                            { "name":"", "qty":"", "rate":"", "amount":"" }
                          ],
                          "total":""
                        }
                        """
                        
                        response = None
                        max_retries = 3
                        retry_delay = 15
                        
                        for attempt in range(max_retries):
                            try:
                                response = model.generate_content([prompt, image])
                                break
                            except Exception as api_err:
                                err_msg = str(api_err)
                                if "429" in err_msg or "quota" in err_msg.lower():
                                    if attempt < max_retries - 1:
                                        st.warning(f"⏳ Rate Limit / Quota Exhausted! Retrying automated pass in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                                        time.sleep(retry_delay)
                                        retry_delay *= 2
                                    else:
                                        st.error("❌ Quota Completely Exhausted for today on Free Tier. Please upgrade to Pay-As-You-Go on Google AI Studio or use a new API Key.")
                                        st.stop()
                                else:
                                    st.error(f"Execution Stop Engine Error: {err_msg}")
                                    st.stop()                      
