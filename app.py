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
import platform
import os

# -------------------------
# PAGE CONFIG & BRANDING
# -------------------------
st.set_page_config(page_title="Deep CSC - AI Bill Processor", page_icon="🧾", layout="wide")

st.markdown("""
    <style>
        .stSidebar { background-color: #0f172a !important; }
        .stButton>button { background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# -------------------------
# HARDWARE MODULE (CLOUD SAFE)
# -------------------------
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        with col_scan:
            if platform.system() == "Windows":
                if st.button("🚀 Trigger Flatbed Scan"):
                    try:
                        os.startfile(r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe")
                        st.success("Launching Brother App...")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.info("Scanner control available on Local Windows only.")
        with col_print:
            if st.button("🖨️ Send to Printer"):
                st.components.v1.html("<script>window.print();</script>", height=0)

# -------------------------
# DATABASE & HELPERS
# -------------------------
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_name TEXT, bill_date TEXT, gst_number TEXT, total REAL, calculated_total REAL, status TEXT, timestamp TEXT)''')
    conn.commit(); conn.close()

init_db()

# -------------------------
# LOGIN SYSTEM
# -------------------------
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("🔐 System Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == "admin" and password == "password123":
            st.session_state.logged_in = True
            st.rerun()
    st.stop()

# -------------------------
# NAVIGATION
# -------------------------
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])
if st.sidebar.button("🚪 Terminate Session"):
    st.session_state.logged_in = False
    st.rerun()

# -------------------------
# MAIN LOGIC
# -------------------------
if app_mode == "📤 Upload & Process":
    st.header("🧾 AI Multi-Bill OCR Processor")
    hardware_module()
    
    uploaded_files = st.file_uploader("Upload Bills", type=["jpg", "png"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            st.image(file, width=300)
            if st.button(f"Process {file.name}"):
                st.write("AI Processing logic here...")

elif app_mode == "📊 Dashboard & History":
    st.header("📊 Dashboard")
    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    st.dataframe(df)
    conn.close()
