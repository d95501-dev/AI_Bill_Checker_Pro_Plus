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
# 1. PAGE SETUP & GLOBAL CONFIG
# -------------------------
st.set_page_config(
    page_title="AI Bill Checker Pro - Premium Operations Terminal",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Enterprise Theme Styling Engine (Dark/Light Balance)
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
        
        * { font-family: 'Plus Jakarta Sans', sans-serif !important; }
        .main { background-color: #f8fafc; }
        
        /* Sidebar Styling Override */
        [data-testid="stSidebar"] {
            background-color: #0b1329 !important;
            box-shadow: 4px 0 24px rgba(0,0,0,0.15);
        }
        [data-testid="stSidebar"] * { color: #f8fafc !important; }
        
        /* Brand Sidebar Box */
        .sidebar-brand-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%) !important;
            padding: 24px !important;
            border-radius: 16px !important;
            text-align: center !important;
            margin-bottom: 25px !important;
            border: 1px solid #334155 !important;
        }
        .sidebar-title { color: #38bdf8 !important; font-size: 24px !important; font-weight: 800 !important; margin: 0; }
        .sidebar-subtitle { color: #ff477e !important; font-size: 11px !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 1.5px !important; margin-top: 4px; }
        
        /* Modern Header Banner */
        .premium-header-card {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 60%, #2e1065 100%);
            padding: 32px;
            border-radius: 20px;
            margin-bottom: 30px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1);
        }
        .premium-header-title { background: linear-gradient(to right, #38bdf8, #a78bfa, #f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0; font-size: 32px !important; font-weight: 800 !important; }
        
        /* Metric Card Widgets */
        div[data-testid="stMetric"] {
            background: #ffffff !important;
            padding: 20px 24px !important;
            border-radius: 16px !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
        }
        div[data-testid="stMetricValue"] { font-size: 32px !important; font-weight: 800 !important; color: #0f172a !important; }
        div[data-testid="stMetricLabel"] { font-size: 11px !important; text-transform: uppercase !important; font-weight: 700 !important; color: #64748b !important; letter-spacing: 0.5px; }
        
        /* Clean Buttons styling */
        .stButton>button {
            background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
            color: white !important; font-weight: 600 !important; border-radius: 10px !important;
            border: none !important; transition: all 0.2s ease;
        }
        .stButton>button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3); }
    </style>
""", unsafe_allow_html=True)

# -------------------------
# 2. SQLITE LOGGING PERSISTENCE ENGINE
# -------------------------
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

def insert_bill(shop, date, gst, total, calc_total, status):
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bills WHERE shop_name=? AND bill_date=? AND total=?", (shop, date, total))
    if cursor.fetchone():
        conn.close()
        return False, "Duplicate billing record skipped to avoid entry pollution."
    
    cursor.execute("""
        INSERT INTO bills (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "Invoice transactional log secured safely in local database ledger!"

# -------------------------
# 3. SECURE ACCESS WALL (PROXY GATEWAY)
# -------------------------
USERNAME = st.secrets.get("APP_USERNAME", "admin")
PASSWORD = st.secrets.get("APP_PASSWORD", "password123")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    with col_l2:
        st.markdown("<div style='text-align: center; margin-top: 80px;'><h1 style='color: #1e3a8a; font-size: 38px; font-weight: 800;'>🛡️ AI BILL CHECKER PRO</h1><p style='color: #64748b;'>Enterprise Verification Pipeline Gateway</p></div>
