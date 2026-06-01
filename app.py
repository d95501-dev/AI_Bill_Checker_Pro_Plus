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
    page_title="Deep CSC - AI Bill Processor Premium",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Global CSS Stylesheet - Fixed Visibility & Maximum Contrast
st.markdown("""
    <style>
        .main { background-color: #f8fafc; }
        h1, h2, h3, h4 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
        
        /* Main Header Custom CSS */
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
        
        /* Metrics Cards */
        div[data-testid="stMetric"] {
            background: #ffffff !important; padding: 24px !important; border-radius: 20px !important;
            box-shadow: 0 12px 20px -3px rgba(15, 23, 42, 0.04) !important;
        }
        div[data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 800 !important; }
        div[data-testid="stMetricLabel"] { font-size: 12px !important; text-transform: uppercase !important; font-weight: 700 !important; color: #64748b !important; }
        
        /* SIDEBAR STYLING FOR MAXIMUM VISIBILITY */
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
            margin: 0 !important;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5) !important;
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
            background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important; color: white !important;
            font-weight: 700 !important; padding: 12px 24px !important; border-radius: 12px !important; border: none !important;
        }
    </style>
""", unsafe_allow_html=True)

# -------------------------
# DATABASE SETUP
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
    duplicate = cursor.fetchone()
    if duplicate:
        conn.close()
        return False, "Duplicate entry detected!"
    cursor.execute("""
        INSERT INTO bills (shop_name, bill_date, gst_number, total, calculated_total, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (shop, date, gst, total, calc_total, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "Successfully logged into DB"

# -------------------------
# LOGIN SYSTEM
# -------------------------
USERNAME = st.secrets.get("APP_USERNAME", "admin")
PASSWORD = st.secrets.get("APP_PASSWORD", "password123")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<div style='text-align: center; padding: 20px;'><h2 style='color: #4f46e5; font-size: 42px; font-weight:900;'>Deep CSC</h2><p style='color: #64748b;'>Authorized Digital Seva AI Portal</p></div>", unsafe_allow_html=True)
    st.title("🔐 System Login Proxy")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login Server", use_container_width=True):
        if username == USERNAME and password == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password Credentials")
    st.stop()

# Initialize session state for direct scanner/camera workflow
if "scanned_bill_img" not in st.session_state:
    st.session_state.scanned_bill_img = None

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

st.sidebar.markdown(f"<p style='color: #cbd5e1; font-family: sans-serif; font-size: 14px; margin-left: 5px;'>Operator: <b style='color:#38bdf8;'>{USERNAME} (Deepak)</b></p>", unsafe_allow_html=True)
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "🖨️ Hardware Control Center", "📊 Dashboard & History"])

st.sidebar.markdown("<br><br><hr style='border-color: #1e293b;'>", unsafe_allow_html=True)
if st.sidebar.button("🚪 Terminate Session", use_container_width=True):
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
    st.error(f"Model Initialization Failed: {e}")
    st.stop()

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
    st.markdown('<div class="deep-csc-header"><div class="branding-text"><h1>🧾 AI Multi-Bill OCR Processor</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by Gemini Vision Core.</p></div><div class="csc-meta-badge">📍 <b>Deep Digital Seva Kendra</b><br>👤 Owner: Deepak | ID: 256423250015</div><div class="branding-badge">Deep CSC AI</div></div>', unsafe_allow_html=True)
    
    source_mode = st.radio("Select Document Input Channel Source", ["📁 File Explorer Local Storage", "🔌 Direct Scanned Memory Buffer"], horizontal=True)
    
    uploaded_files = []
    if source_mode == "📁 File Explorer Local Storage":
        uploaded_files = st.file_uploader("Drop batch bill images below (Multi-upload supported)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    else:
        if st.session_state.scanned_bill_img is not None:
            st.info("✅ Active hardware document bridge input detected inside cache memory registry.")
            uploaded_files = [st.session_state.scanned_bill_img]
        else:
            st.warning("⚠️ Hardware bridge empty. Please go to '🖨️ Hardware Control Center' tab to scan or capture a document first.")

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            st.markdown("---")
            if source_mode == "📁 File Explorer Local Storage":
                file_name_label = file.name
                image = Image.open(file)
            else:
                file_name_label = f"Live_Hardware_Capture_Bundle_{idx+1}.png"
                image = file

            st.subheader(f"📄 Processing Block [{idx+1}]: {file_name_label}")
            col_img, col_act = st.columns([1, 2], gap="large")
            
            with col_img:
                st.image(image, caption=f"Source: {file_name_label}", use_container_width=True)
                
            with col_act:
                if st.button(f"⚡ Execute AI Analysis", key=f"btn_{idx}", use_container_width=True):
                    with st.spinner("AI engine parsing structural metadata..."):
                        prompt = "Analyze this bill image. Extract shop_name, bill_date, gst_number, items (name, qty, rate, amount), and total. Return data ONLY as a valid JSON object matching these keys."
                        
                        response = None
                        max_retries = 3
                        retry_delay = 5
                        
                        for attempt in range(max_retries):
                            try:
                                response = model.generate_content([prompt, image])
                                break
                            except Exception as api_err:
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay)
                                else:
                                    st.error(f"Engine Core Crash: {str(api_err)}")
                                    st.stop()

                        if response:
                            try:
                                text = response.text.strip().replace("```json", "").replace("```", "")
                                match = re.search(r"\{.*\}", text, re.DOTALL)
                                if match:
                                    text = match.group(0)
                                    
                                data = json.loads(text)
                                shop_name = data.get("shop_name", "Unknown Shop")
                                bill_date = data.get("bill_date", datetime.now().strftime("%Y-%m-%d"))
                                gst_number = data.get("gst_number", "N/A")
                                
                                st.markdown(f"### 🏪 Vendor: `{shop_name}`")
                                c1, c2 = st.columns(2)
                                c1.markdown(f"**🗓️ Declared Invoice Date:** {bill_date}")
                                
                                is_valid_gst, formatted_gst = validate_gst(gst_number)
                                if gst_number != "N/A" and is_valid_gst:
                                    c2.markdown(f"**🛡️ GSTIN Registry Validation:** :green
