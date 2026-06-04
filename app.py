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
import os
import subprocess  # Subprocess import kiya gaya hai NAPS2 run karne ke liye

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
DEFAULT_USERNAME = st.secrets.get("APP_USERNAME", "admin")
DEFAULT_PASSWORD = st.secrets.get("APP_PASSWORD", "password123")
NAPS2_PATH = r"C:\Program Files\NAPS2\NAPS2.exe"  # NAPS2 executable ka path

def setup_page():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="expanded"
    )

def apply_css():
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
            div[data-testid="stMetric"] {
                background: #ffffff !important; padding: 24px !important; border-radius: 20px !important;
                box-shadow: 0 12px 20px -3px rgba(15, 23, 42, 0.04) !important;
            }
            div[data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 800 !important; }
            div[data-testid="stMetricLabel"] { font-size: 12px !important; text-transform: uppercase !important; font-weight: 700 !important; color: #64748b !important; }
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
            .sidebar-title {
                color: #38bdf8 !important;
                font-size: 28px !important;
                font-weight: 900 !important;
                margin: 0 0 6px 0 !important;
                letter-spacing: 0.5px !important;
            }
            .sidebar-subtitle {
                color: #ff477e !important;
                font-size: 14px !important;
                font-weight: 800 !important;
                text-transform: uppercase !important;
                letter-spacing: 1px !important;
                margin-bottom: 12px !important;
            }
            .sidebar-id-badge {
                color: #ffffff !important;
                font-size: 13px !important;
                font-weight: 700 !important;
                font-family: monospace !important;
                background: #1e293b !important;
                padding: 6px 12px !important;
                border-radius: 8px !important;
                display: inline-block !important;
                border: 1px solid #475569 !important;
            }
            .stButton>button {
                background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
                color: white !important;
                font-weight: 700 !important;
                padding: 12px 24px !important;
                border-radius: 12px !important;
                border: none !important;
            }
        </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            bill_date TEXT NOT NULL,
            gst_number TEXT,
            total REAL NOT NULL,
            calculated_total REAL NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(shop_name, bill_date, total)
        )
    """)
    conn.commit()
    conn.close()

def insert_bill(shop, date, gst, total, calc_total, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO bills
            (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            shop, date, gst, total, calc_total, status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Duplicate entry detected!"
        return True, "Successfully logged into DB"
    finally:
        conn.close()

def init_auth():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

def do_login():
    st.markdown(
        "<div style='text-align:center; padding:20px;'><h2 style='color:#4f46e5; font-size:42px; font-weight:900;'>Deep CSC</h2><p style='color:#64748b;'>Authorized Digital Seva AI Portal</p></div>",
        unsafe_allow_html=True
    )
    st.title("🔐 System Login Proxy")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login Server", use_container_width=True):
        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password Credentials")
    st.stop()

def terminate_session():
    st.session_state.logged_in = False
    for k in list(st.session_state.keys()):
        if k != "logged_in":
            del st.session_state[k]
    st.rerun()

def setup_gemini():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        st.error("Please configure GEMINI_API_KEY in your Streamlit secrets.")
        st.stop()
    genai.configure(api_key=api_key)
    try:
        return genai.GenerativeModel("gemini-2.5-flash")
    except Exception as e:
        st.error(f"Model Initialization Failed: {e}")
        st.stop()

def validate_gst(gst_str):
    if not gst_str:
        return False, "N/A"
    gst_regex = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    clean_gst = re.sub(r'[^A-Z0-9]', '', str(gst_str).upper())
    return bool(re.match(gst_regex, clean_gst)), clean_gst

def normalize_items(items):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for it in items:
        if isinstance(it, dict):
            cleaned.append({
                "name": it.get("name") or "",
                "qty": it.get("qty") or "",
                "rate": it.get("rate") or "",
                "amount": it.get("amount") or ""
            })
    return cleaned

def parse_json_from_response(response_text):
    if not response_text:
        raise ValueError("Empty response from model")
    raw = response_text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return json.loads(raw)

def analyze_bill(model, file_payload):
    prompt = """
    Return only valid JSON with:
    {
      "shop_name": string or null,
      "bill_date": string or null,
      "gst_number": string or null,
      "items": [{"name": string, "qty": number/string, "rate": number/string, "amount": number/string}],
      "total": number/string or null
    }
    No markdown, no explanation, no extra text.
    """
    last_error = None
    for attempt in range(3):
        try:
            response = model.generate_content([prompt, file_payload])
            text = getattr(response, "text", None)
            return parse_json_from_response(text)
        except Exception
