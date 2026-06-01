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

# Premium Custom CSS Injection for Modern Fluid Layout
st.markdown("""
    <style>
        /* Global Reset and Background */
        .main { background: #fdfeff; }
        h1, h2, h3 { font-family: 'Inter', system-ui, sans-serif; color: #0f172a !important; font-weight: 800 !important; }
        
        /* Glassmorphism Metric Cards Design */
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            padding: 24px;
            border-radius: 16px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.04), 0 4px 6px -4px rgba(0, 0, 0, 0.04);
            border: 1px solid #e2e8f0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.08);
            border-color: #cbd5e1;
        }
        div[data-testid="stMetricValue"] {
            font-size: 34px !important;
            font-weight: 800 !important;
            color: #4f46e5 !important;
            letter-spacing: -0.5px;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 13px !important;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            font-weight: 700 !important;
            color: #64748b !important;
            margin-bottom: 6px;
        }
        
        /* Custom Stylish Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%) !important;
            color: white !important;
            font-weight: 600 !important;
            padding: 12px 24px !important;
            border-radius: 12px !important;
            border: none !important;
            box-shadow: 0 4px 10px rgba(79, 70, 229, 0.25) !important;
            transition: all 0.2s ease !important;
        }
        .stButton>button:hover {
            transform: translateY(-2px) scale(1.01) !important;
            box-shadow: 0 10px 20px rgba(79, 70, 229, 0.35) !important;
        }
        
        /* Clean Sidebar Styles */
        .css-17o0z9e, .stSidebar { background-color: #0f172a !important; }
        .block-container { padding-top: 2rem !important; }
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
    st.title("🔐 AI Bill Checker Login", text_alignment="center")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):
        if username == USERNAME and password == PASSWORD:
            st.
