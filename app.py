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

# 1. PAGE SETUP & GLOBAL CONFIG
st.set_page_config(page_title="AI Bill Checker Pro", layout="wide")

# CSS Injection
st.markdown("""
    <style>
        .premium-header-card {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 60%, #2e1065 100%);
            padding: 32px;
            border-radius: 20px;
            color: white;
        }
        .premium-header-title { color: #38bdf8; font-size: 32px; font-weight: 800; }
    </style>
""", unsafe_allow_html=True)

# 2. DATABASE INITIALIZATION
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute("""
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
    """)
    conn.commit()
    conn.close()

init_db()

# 3. SECURITY GATEWAY
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🛡️ AI BILL CHECKER PRO</h1>", unsafe_allow_html=True)
    with st.form("Login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if u == "admin" and p == "admin":
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Invalid Credentials")
    st.stop()

# 4. MAIN APP LOGIC
st.sidebar.title("AI BILL CHECKER")
app_mode = st.sidebar.radio("Navigation", ["Dashboard", "OCR Engine"])

# Initialize Gemini
genai.configure(api_key="YOUR_ACTUAL_API_KEY") # Yaha apna key daalein
model = genai.GenerativeModel("gemini-1.5-flash")

if app_mode == "Dashboard":
    st.markdown('<div class="premium-header-card"><h1 class="premium-header-title">📊 Operations Dashboard</h1></div>', unsafe_allow_html=True)
    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    conn.close()
    st.dataframe(df)

elif app_mode == "OCR Engine":
    st.markdown('<div class="premium-header-card"><h1 class="premium-header-title">📤 Document OCR Engine</h1></div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload bill", type=["jpg", "png"])
    
    if uploaded_file:
        st.image(uploaded_file)
        if st.button("Process Bill"):
            # Yaha aapka AI processing code ayega
            st.success("Bill processed successfully!")
            # Example f-string fix
            status = "Verified"
            st.error(f"Audit Status: {status}") 

# Footer
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()
