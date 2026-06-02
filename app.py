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
import subprocess
import os

# -------------------------
# PAGE CONFIG & BRANDING
# -------------------------
st.set_page_config(
    page_title="Deep CSC - AI Bill Processor Premium",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Global CSS Stylesheet
st.markdown("""
    <style>
        .main { background-color: #f8fafc; }
        h1, h2, h3, h4 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
        
        .deep-csc-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            padding: 30px; border-radius: 24px; margin-bottom: 35px;
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
            text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 4px 14px rgba(236, 72, 153, 0.4);
        }
        .stSidebar { background-color: #0f172a !important; }
        .sidebar-brand-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%) !important; 
            padding: 22px !important; 
            border-radius: 16px !important; 
            text-align: center !important; 
            margin-bottom: 20px !important; 
            border: 2px solid #334155 !important; 
            box-shadow: 0 6px 12px rgba(0,0,0,0.4) !important;
        }
        .sidebar-title { color: #38bdf8 !important; font-size: 28px !important; font-weight: 900 !important; margin: 0 0 6px 0 !important; }
        .sidebar-subtitle { color: #ff477e !important; font-size: 14px !important; font-weight: 800 !important; text-transform: uppercase !important; }
        .sidebar-id-badge { color: #ffffff !important; font-size: 13px !important; font-family: monospace !important; background: #1e293b !important; padding: 6px 12px !important; border-radius: 8px !important; border: 1px solid #475569 !important; }
    </style>
""", unsafe_allow_html=True)

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
    cursor.execute("SELECT id FROM bills WHERE shop_name=? AND bill_date=? AND total=?", (shop, date, total))
    if cursor.fetchone():
        conn.close()
        return False, "Duplicate entry detected!"
    cursor.execute('''
        INSERT INTO bills (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "Successfully logged into DB"

# -------------------------
# LOGIN SYSTEM
# -------------------------
USERNAME = st.secrets.get("APP_USERNAME", "admin")
PASSWORD = st.secrets.get("APP_PASSWORD", "password123")

if "logged_in" not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 System Login Proxy")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login Server"):
        if username == USERNAME and password == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else: st.error("Invalid Credentials")
    st.stop()

# -------------------------
# SIDEBAR NAVIGATION
# -------------------------
st.sidebar.markdown("""
    <div class="sidebar-brand-box">
        <div class="sidebar-title">Deep CSC</div>
        <div class="sidebar-subtitle">Deep Digital Seva Kendra</div>
        <div class="sidebar-id-badge">ID: 256423250015</div>
    </div>
""", unsafe_allow_html=True)
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

# -------------------------
# HARDWARE MODULE (UPDATED)
# -------------------------
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        with col_scan:
            st.markdown("#### 📷 Scanner Interface")
            if st.button("🚀 Open Brother Scanner"):
                brother_path = r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe"
                if os.path.exists(brother_path):
                    subprocess.Popen([brother_path])
                    st.success("✅ Brother iPrint&Scan launched")
                else: st.error("Brother iPrint&Scan not found")
            if st.button("📄 Open NAPS2 Scanner"):
                naps2_path = r"C:\Program Files\NAPS2\NAPS2.exe"
                if os.path.exists(naps2_path):
                    subprocess.Popen([naps2_path])
                    st.success("✅ NAPS2 launched")
                else: st.error("NAPS2 not found")
        with col_print:
            st.markdown("#### 🖨️ Printer Interface")
            printer_name = st.selectbox("Select Printer", ["Brother DCP-T820DW", "Default System Printer"])
            if st.button("🖨️ Print"):
                st.info(f"Sending document to {printer_name}")

# -------------------------
# MODULE 1: UPLOAD & PROCESS
# -------------------------
if app_mode == "📤 Upload & Process":
    st.markdown('<div class="deep-csc-header"><h1>🧾 AI Multi-Bill OCR Processor</h1></div>', unsafe_allow_html=True)
    hardware_module()
    uploaded_files = st.file_uploader("Drop batch bill images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    # ... (Rest of your processing logic here) ...

# -------------------------
# MODULE 2: DASHBOARD & HISTORY
# -------------------------
elif app_mode == "📊 Dashboard & History":
    st.markdown('<div class="deep-csc-header"><h1>📊 Financial Operations Command Center</h1></div>', unsafe_allow_html=True)
    # ... (Dashboard logic here) ...
