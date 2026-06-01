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
    page_title="Deep CSC - Bill Processor Pro",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------
# ULTRA-CLEAN MODERN CSS (ZERO OVERLAP)
# -------------------------
st.markdown("""
    <style>
        /* Main background and clean typography */
        .main { background-color: #f8fafc; }
        h1, h2, h3, h4 { font-family: 'Inter', system-ui, sans-serif !important; font-weight: 700 !important; }
        
        /* Modern Top Bar Integration */
        .top-navbar {
            background-color: #ffffff;
            padding: 15px 25px;
            border-radius: 16px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid #e2e8f0;
        }
        .nav-brand { display: flex; align-items: center; gap: 12px; }
        .nav-logo-text { font-size: 22px !important; font-weight: 800 !important; color: #1e40af !important; margin: 0; }
        .nav-badge { background-color: #eff6ff; color: #1e40af; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
        .user-profile-box { text-align: right; line-height: 1.3; }
        .user-name { font-size: 14px; font-weight: 700; color: #1e293b; }
        .user-meta { font-size: 11px; color: #64748b; font-family: monospace; }
        
        /* Clean Sidebar Override */
        [data-testid="stSidebar"] {
            background-color: #0f172a !important;
        }
        [data-testid="stSidebar"] *, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
            color: #f1f5f9 !important;
        }
        
        /* Premium Metrics Cards */
        div[data-testid="stMetric"] {
            background: #ffffff !important; padding: 20px !important; border-radius: 16px !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
            border: 1px solid #e2e8f0 !important;
        }
        div[data-testid="stMetricValue"] { font-size: 32px !important; font-weight: 700 !important; color: #1e293b !important; }
        div[data-testid="stMetricLabel"] { font-size: 12px !important; text-transform: uppercase !important; font-weight: 600 !important; color: #64748b !important; }
        
        /* Action Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important; color: white !important;
            font-weight: 600 !important; padding: 10px 20px !important; border-radius: 10px !important; border: none !important;
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
    cursor.execute("SELECT id FROM bills WHERE shop_name=? AND bill_date=? AND total=?", (shop, date, total))
    duplicate = cursor.fetchone()
    if duplicate:
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

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<div style='text-align: center; padding: 40px 0 20px 0;'><h2 style='color: #2563eb; font-size: 36px;'>Deep CSC Portal</h2><p style='color: #64748b;'>Secure Automated AI Engine</p></div>", unsafe_allow_html=True)
    st.title("🔐 Authentication Required")
    username = st.text_input("Username Key")
    password = st.text_input("Password Key", type="password")

    if st.button("Access Dashboard", use_container_width=True):
        if username == USERNAME and password == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Username or Password Credentials")
    st.stop()

# -------------------------
# GEMINI ENGINE CONFIG
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

# -------------------------
# SIDEBAR NAVIGATION
# -------------------------
st.sidebar.title("🎛️ Control Center")
st.sidebar.markdown("---")
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)
if st.sidebar.button("🚪 Log Out", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# -------------------------
# RENDER GLOBAL HEADER
# -------------------------
st.markdown(f"""
    <div class="top-navbar">
        <div class="nav-brand">
            <div class="nav-logo-text">AI Bill Checker Pro</div>
            <div class="nav-badge">V2.5 Premium</div>
        </div>
        <div class="user-profile-box">
            <div class="user-name">Deepak Kumar (admin)</div>
            <div class="user-meta">CSC ID: 256423250015 | Jagadhri</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# -------------------------
# MODULE 1: UPLOAD & PROCESS
# -------------------------
if app_mode == "📤 Upload & Process":
    st.markdown("<h3>📤 Extract Invoice Data</h3>", unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        "Choose bill images to analyze:",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            st.markdown(f"#### 📄 File Panel: {file.name}")
            
            image = Image.open(file)
            col_img, col_act = st.columns([1, 2], gap="large")
            
            with col_img:
                st.image(image, caption="Uploaded Document", use_container_width=True)
                
            with col_act:
                if st.button(f"⚡ Start AI Processing", key=f"btn_{idx}", use_container_width=True):
                    with st.spinner("AI parsing text logs..."):
                        prompt = "Analyze this bill. Extract shop_name, bill_date, gst_number, items (name, qty, rate, amount), and total. Return strictly as raw JSON object only."
                        
                        try:
                            response = model.generate_content([prompt, image])
                            text = response.text.strip().replace("```json", "").replace("```", "")
                            match = re.search(r"\{.*\}", text, re.DOTALL)
                            if match:
                                text = match.group(0)
                                
                            data = json.loads(text)
                            shop_name = data.get("shop_name", "Unknown Shop")
                            bill_date = data.get("bill_date", datetime.now().strftime("%Y-%m-%d"))
                            gst_number = data.get("gst_number", "N/A")
                            
                            st.markdown(f"### 🏪 Shop: **{shop_name}**")
                            st.markdown(f"🗓️ **Date:** {bill_date} | 🛡️ **GSTIN:** {gst_number}")
                            
                            items = data.get("items", [])
                            if items:
                                df = pd.DataFrame(items)
                                st.dataframe(df, use_container_width=True, hide_index=True)
                                if "amount" in df.columns:
                                    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
                                calculated_total = float(df["amount"].sum())
                            else:
                                calculated_total = 0.0
                                
                            try:
                                bill_total = float(str(data.get("total", 0)).replace(',', ''))
                            except:
                                bill_total = 0.0
                                
                            diff = abs(calculated_total - bill_total)
                            status_txt = "Matched" if diff < 1 else "Mismatch"
                            
                            c1, c2 = st.columns(2)
                            c1.metric("Calculated Total", f"₹{calculated_total:,.2f}")
                            c2.metric("Declared Total", f"₹{bill_total:,.2f}")
                            
                            if status_txt == "Matched":
                                st.success("🎯 Audit Success: Totals match perfectly.")
                            else:
                                st.error(f"🛑 Audit Mismatch Detected! Gap: ₹{diff:,.2f}")
                                
                            saved, db_msg = insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt)
                            st.toast(db_msg)
                            
                            # Export Actions
                            excel_buffer = BytesIO()
                            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                                pd.DataFrame(items).to_excel(writer, index=False)
                                
                            st.download_button("📥 Export Excel", data=excel_buffer.getvalue(), file_name=f"{shop_name}.xlsx", mime="application/vnd.ms-excel")
                                
                        except Exception as parse_err:
                            st.error(f"Parsing Error: {str(parse_err)}")

# -------------------------
# MODULE 2: DASHBOARD & HISTORY
# -------------------------
elif app_mode == "📊 Dashboard & History":
    st.markdown("<h3>📊 Data Analytics Center</h3>", unsafe_allow_html=True)
    
    conn = sqlite3.connect("bills.db")
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()
    
    if df_db.empty:
        st.info("No bills scanned yet. Go to Upload section to start!")
    else:
        total_spent = df_db["total"].sum()
        total_invoices = len(df_db)
        mismatched_count = len(df_db[df_db["status"] == "Mismatch"])
        
        db1, db2, db3 = st.columns(3)
        db1.metric("Total Processed Volume", f"₹{total_spent:,.2f}")
        db2.metric("Total Invoices Scanned", f"{total_invoices} Bills")
        db3.metric("Mismatched Invoices", f"{mismatched_count}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Central Registry Table
        st.markdown("#### 🔍 Master Registry Record Logs")
        search_query = st.text_input("Filter records by Shop Name:")
        if search_query:
            df_db = df_db[df_db["shop_name"].str.contains(search_query, case=False, na=False)]
            
        st.dataframe(df_db, use_container_width=True, hide_index=True)
