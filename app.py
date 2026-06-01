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
# PAGE CONFIG & BRANDING
# -------------------------
st.set_page_config(
    page_title="AI Bill Checker Premium",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Custom CSS Injection for Modern Dashboard Theme
st.markdown("""
    <style>
        /* Global Background and Typography styling */
        .main { background-color: #f8fafc; }
        h1, h2, h3 { font-family: 'Inter', system-ui, sans-serif; color: #0f172a !important; font-weight: 800 !important; }
        
        /* Glassmorphism Metric Cards styling */
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
            padding: 24px;
            border-radius: 16px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.04), 0 4px 6px -4px rgba(0, 0, 0, 0.04);
            border: 1px solid #e2e8f0;
            transition: transform 0.2s ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.06);
        }
        div[data-testid="stMetricValue"] {
            font-size: 32px !important;
            font-weight: 800 !important;
            color: #4f46e5 !important;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 13px !important;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 700 !important;
            color: #64748b !important;
        }
        
        /* Modern Solid Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%) !important;
            color: white !important;
            font-weight: 600 !important;
            padding: 10px 20px !important;
            border-radius: 10px !important;
            border: none !important;
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3) !important;
        }
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
st.sidebar.markdown("<h2 style='font-size: 18px; color: #f8fafc; margin-bottom: 5px;'>🏢 Control Center</h2>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='color: #94a3b8;'>Active Profile: <b>{USERNAME}</b></p>", unsafe_allow_html=True)
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

st.sidebar.markdown("<br><hr>", unsafe_allow_html=True)
if st.sidebar.button("🚪 Terminate Session", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# -------------------------
# GEMINI SETUP
# -------------------------
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    st.error
