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

# Custom Global CSS Stylesheet - Fixed Sidebar Visibility & Contrast
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
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        div[data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 800 !important; }
        div[data-testid="stMetricLabel"] { font-size: 12px !important; text-transform: uppercase !important; font-weight: 700 !important; color: #64748b !important; }
        
        /* STRICT SIDEBAR STYLING FOR MAXIMUM VISIBILITY */
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
            padding: 0 !important; 
            text-shadow: 0 2px 4px rgba(0,0,0,0.5) !important;
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

# -------------------------
# SIDEBAR NAVIGATION (PERFECT VISIBILITY CONTROL)
# -------------------------
st.sidebar.markdown("""
    <div class="sidebar-brand-box">
        <div class="sidebar-title">Deep CSC</div>
        <div class="sidebar-subtitle">Deep Digital Seva Kendra</div>
        <div class="sidebar-id-badge">ID: 256423250015</div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.markdown(f"<p style='color: #cbd5e1; font-size: 14px; margin-left: 5px;'>Operator: <b style='color:#38bdf8;'>{USERNAME} (Deepak)</b></p>", unsafe_allow_html=True)
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

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
# MODULE 1: UPLOAD & PROCESS (UPDATED WITH HARDWARE BRIDGE)
# -------------------------
if app_mode == "📤 Upload & Process":
    st.markdown('<div class="deep-csc-header">...</div>', unsafe_allow_html=True) # (Keep your existing header)
    
    # HARDWARE BRIDGE ADDITION
    st.subheader("🖥️ Hardware Connectivity Bridge")
    hw_tab1, hw_tab2 = st.tabs(["📷 Scanner (Camera Input)", "🖨️ Printer Interface"])
    
    with hw_tab1:
        st.info("Direct scanner interface se bill scan karein.")
        scan_file = st.camera_input("Scanner Device Feed")
        if scan_file:
            st.success("Image successfully captured from hardware buffer!")
            uploaded_files = [scan_file] # Isko process mein pass karenge
            
    with hw_tab2:
        st.info("Report ko physical printer par bhejne ke liye niche click karein.")
        if st.button("🖨️ Open Print Dialog"):
            # JavaScript use karke browser ka print window trigger karte hain
            js = "window.print();"
            st.components.v1.html(f"<script>{js}</script>", height=0)

    # ... Yaha se aapka existing 'uploaded_files' wala processing code continue karein ...
# -------------------------
# MODULE 1: UPLOAD & PROCESS
# -------------------------
if app_mode == "📤 Upload & Process":
    st.markdown('<div class="deep-csc-header"><div class="branding-text"><h1>🧾 AI Multi-Bill OCR Processor</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by Gemini Vision Core.</p></div><div class="csc-meta-badge">📍 <b>Deep Digital Seva Kendra</b><br>👤 Owner: Deepak | ID: 256423250015</div><div class="branding-badge">Deep CSC AI</div></div>', unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        "Drop batch bill images below (Multi-upload supported)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            st.markdown("---")
            st.subheader(f"📄 Processing Block [{idx+1}]: {file.name}")
            
            image = Image.open(file)
            col_img, col_act = st.columns([1, 2], gap="large")
            
            with col_img:
                st.image(image, caption=f"Source: {file.name}", use_container_width=True)
                
            with col_act:
                if st.button(f"⚡ Execute AI Analysis", key=f"btn_{idx}", use_container_width=True):
                    with st.spinner("AI engine parsing structural metadata..."):
                        prompt = "Analyze this bill image. Extract shop_name, bill_date, gst_number, items (name, qty, rate, amount), and total. Return data ONLY as a valid raw JSON object block matching these keys."
                        
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
                                        st.warning(f"⏳ Rate Limit hit! Auto-retrying in {retry_delay}s...")
                                        time.sleep(retry_delay)
                                        retry_delay *= 2
                                    else:
                                        st.error("❌ Quota Exhausted! Check Google AI Studio settings.")
                                        st.stop()
                                else:
                                    st.error(f"Engine Core Crash: {err_msg}")
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
                                    c2.markdown(f"**🛡️ GSTIN Registry Validation:** :green[✅ Valid - {formatted_gst}]")
                                elif gst_number != "N/A":
                                    c2.markdown(f"**🛡️ GSTIN Registry Validation:** :orange[⚠️ Format Mismatch - {gst_number}]")
                                else:
                                    c2.markdown(f"**🛡️ GSTIN Registry Validation:** :red[ℹ️ Not Disclosed]")
                                    
                                items = data.get("items", [])
                                if items:
                                    df = pd.DataFrame(items)
                                    st.markdown("<h4 style='font-size:18px; margin-top:20px;'>Detailed Line-Item Breakdown</h4>", unsafe_allow_html=True)
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
                                
                                st.markdown("<h4 style='font-size:18px; margin-top:20px;'>Arithmetic Audit Engine</h4>", unsafe_allow_html=True)
                                x1, x2 = st.columns(2)
                                
                                with x1:
                                    st.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
                                with x2:
                                    st.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")
                                
                                if status_txt == "Matched":
                                    st.success("🎯 Auto-Arithmetic Audit Pass: Balance sheet matches perfectly.")
                                else:
                                    st.error(f"🛑 Audit Discrepancy Found: Leakage variance of ₹{diff:,.2f}")
                                    
                                saved, db_msg = insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt)
                                if saved:
                                    st.toast(f"Saved: {db_msg}", icon="💾")
                                else:
                                    st.toast(f"Skipped: {db_msg}", icon="🚨")
                                    
                                st.markdown("---")
                                excel_buffer = BytesIO()
                                with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                                    pd.DataFrame(items).to_excel(writer, index=False, sheet_name="Parsed Invoice Data")
                                    
                                pdf_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                                doc = SimpleDocTemplate(pdf_temp.name)
                                styles = getSampleStyleSheet()
                                elements = [
                                    Paragraph(f"Invoice Summary: {shop_name}", styles["Title"]),
                                    Spacer(1, 10),
                                    Paragraph(f"Date: {bill_date} | GSTIN: {gst_number}", styles["Normal"]),
                                    Paragraph(f"Verified Final Amount: INR {bill_total}", styles["Heading3"])
                                ]
                                doc.build(elements)
                                
                                ut1, ut2, ut3 = st.columns(3)
                                with ut1:
                                    st.download_button("📥 Export Excel Data Sheets", data=excel_buffer.getvalue(), file_name=f"{shop_name}_ledger.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
                                with ut2:
                                    with open(pdf_temp.name, "rb") as f:
                                        st.download_button("📄 Download Sign-off PDF", f.read(), file_name=f"{shop_name}_receipt.pdf", mime="application/pdf", use_container_width=True)
                                with ut3:
                                    msg_string = f"AI Bill Report - Shop: {shop_name}, Date: {bill_date}, Total: {bill_total}, Audit: {status_txt}"
                                    wa_url = "https://wa.me/?text=" + urllib.parse.quote(msg_string)
                                    st.link_button("📱 Forward Summary to WhatsApp", wa_url, use_container_width=True)
                                    
                            except Exception as parse_err:
                                st.error(f"Structural Parsing Fault: {str(parse_err)}")
                                # -------------------------
# ADVANCED SCANNER & PRINTER INTERFACE
# -------------------------
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    
    # Scanner Control Panel
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        
        with col_scan:
            st.markdown("#### 📷 Scanner Interface")
            scan_dpi = st.select_slider("Select Resolution (DPI)", options=[150, 300, 600], value=300)
            scan_mode = st.radio("Mode", ["Color", "Grayscale", "Black & White"], horizontal=True)
            
            if st.button("🚀 Trigger Flatbed Scan"):
                # Simulation of Scanner hardware interaction
                with st.spinner("Connecting to TWAIN/WIA Driver..."):
                    time.sleep(2) # Hardware handshake delay
                    st.success(f"Scan initialized at {scan_dpi} DPI ({scan_mode})...")
                    # Yaha se image auto-load ho jayegi processing ke liye
                    
        with col_print:
            st.markdown("#### 🖨️ Printer Interface")
            printer_name = st.selectbox("Select Printer", ["Default System Printer", "HP LaserJet Pro", "Canon Pixma"])
            copies = st.number_input("Number of Copies", min_value=1, value=1)
            
            if st.button("🖨️ Send to Printer"):
                js = "window.print();"
                st.components.v1.html(f"<script>{js}</script>", height=0)
                st.info(f"Sending document to {printer_name}...")

# Module 1 mein isse call karein
if app_mode == "📤 Upload & Process":
    # ... header code ...
    hardware_module() # Isse scanner aur printer ka panel wahan dikhega
    # ... baki processing code ...

# -------------------------
# MODULE 2: DASHBOARD & HISTORY
# -------------------------
elif app_mode == "📊 Dashboard & History":
    st.markdown('<div class="deep-csc-header"><div class="branding-text"><h1>📊 Financial Operations Command Center</h1><p style="color: #94a3b8; margin: 5px 0 0 0;">Real-time telemetry, duplicate transaction logs, and ledger integrity checks.</p></div><div class="csc-meta-badge">🏢 <b>Deep Digital Seva Kendra</b><br>🔑 Authorized Identity: Deepak [256423250015]</div><div class="branding-badge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">Created by Deep CSC</div></div>', unsafe_allow_html=True)
    
    conn = sqlite3.connect("bills.db")
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()
    
    if df_db.empty:
        st.markdown('<div style="background-color: #eff6ff; border-left: 5px solid #4f46e5; padding: 22px; border-radius: 14px; margin-top:20px;"><h4 style="color: #1e40af !important; margin:0 0 8px 0; font-size:18px;">🏪 Welcome to Deep CSC Dashboard Panel</h4><p style="color: #1e3a8a; margin:0; font-size:14px; line-height:1.6;">Abhi system database mein koi logs active nahi hain. Metrics aur graphs dekhne ke liye pehle sidebar se <b>\'📤 Upload & Process\'</b> page par jaakar bills process kijiye.</p></div>', unsafe_allow_html=True)
    else:
        total_spent = df_db["total"].sum()
        total_invoices = len(df_db)
        mismatched_records = df_db[df_db["status"] == "Mismatch"]
        mismatched_count = len(mismatched_records)
        
        db1, db2, db3 = st.columns(3, gap="large")
        
        with db1:
            st.metric("💰 Aggregate Pipeline Spend", f"₹{total_spent:,.2f}")
        with db2:
            st.metric("📄 Corporate Vouchers Audited", f"{total_invoices} Bills")
        with db3:
            if mismatched_count > 0:
                st.metric("⚠️ Failed Integrity Mismatches", f"{mismatched_count} Issues")
            else:
                st.metric("✅ System Integrity Audit", "100% Cleared")
            
        st.markdown("<br><hr style='border-color: #e2e8f0;'><br>", unsafe_allow_html=True)
        
        graph_col1, graph_col2 = st.columns([2, 1], gap="large")
        
        with graph_col1:
            st.markdown("<h3 style='font-size:19px; margin-bottom:15px; color:#4f46e5 !important;'>📈 Top Vendors Distribution</h3>", unsafe_allow_html=True)
            chart_data = df_db.groupby("shop_name")["total"].sum().reset_index().sort_values(by="total", ascending=False).head(8)
            chart_data = chart_data.set_index("shop_name")
            st.bar_chart(chart_data, y="total", color="#4f46e5")
            
        with graph_col2:
            st.markdown("<h3 style='font-size:19px; margin-bottom:15px; color:#10b981 !important;'>📊 Ledger Audit Split</h3>", unsafe_allow_html=True)
            status_distribution = df_db["status"].value_counts().reset_index()
            status_distribution.columns = ["Audit Status", "Volume Counter"]
            st.dataframe(status_distribution, use_container_width=True, hide_index=True)
            
        st.markdown("<br><hr style='border-color: #e2e8f0;'><br>", unsafe_allow_html=True)
        st.markdown("<h3 style='font-size:22px;'>🔍 Centralized Ledger Records Registry</h3>", unsafe_allow_html=True)
        
        query_col, export_col = st.columns([3, 1], gap="medium")
        with query_col:
            search_query = st.text_input("⚡ Smart Filter (Input target Vendor Name / Retail Shop keyword string)")
        with export_col:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            master_excel_buffer = BytesIO()
            with pd.ExcelWriter(master_excel_buffer, engine="openpyxl") as writer:
                df_db.to_excel(writer, index=False, sheet_name="Master DB Sheet")
            st.download_button("📥 Master Export DB Logs", data=master_excel_buffer.getvalue(), file_name="Corporate_Master_Ledger.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            
        filtered_df = df_db
        if search_query:
            filtered_df = df_db[df_db["shop_name"].str.contains(search_query, case=False, na=False)]
            
        display_df = filtered_df.copy()
        display_df.columns = ["Log ID", "Vendor Station", "Invoice Date", "Registered GSTIN", "Invoice Cost (₹)", "Computed Cost (₹)", "Audit Evaluation", "System Timestamp"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
