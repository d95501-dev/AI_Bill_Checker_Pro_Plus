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
    page_title="AI Bill Checker Premium | Deep CSC",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Deep CSC Ultimate Colorful UI/UX Premium Stylesheet
st.markdown("""
    <style>
        /* Modern Fluid Theme Reset */
        .main { background-color: #f8fafc; }
        h1, h2, h3, h4 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
        
        /* Deep CSC Premium Dynamic Branding Header */
        .deep-csc-header {
            background: linear-gradient(135deg, #1e1b4b 0%, #311042 100%);
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            margin-bottom: 35px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .branding-text h1 { color: #ffffff !important; margin: 0; font-size: 32px !important; letter-spacing: -0.5px; }
        .branding-badge {
            background: linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%);
            color: white !important;
            padding: 6px 16px;
            border-radius: 50px;
            font-size: 13px !important;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            box-shadow: 0 4px 12px rgba(6, 182, 212, 0.3);
        }
        
        /* Colorful Glowing Dashboard Metrics Cards */
        div[data-testid="stMetric"] {
            background: #ffffff !important;
            padding: 24px !important;
            border-radius: 18px !important;
            box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.04), 0 4px 6px -4px rgba(15, 23, 42, 0.04) !important;
            border-top: 6px solid #4f46e5 !important; /* Default Color Bar */
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.08) !important;
        }
        /* Specific Border-colors for colorful division */
        col-spent div[data-testid="stMetric"] { border-top-color: #4f46e5 !important; }
        
        div[data-testid="stMetricValue"] {
            font-size: 34px !important;
            font-weight: 800 !important;
            letter-spacing: -1px;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 12px !important;
            text-transform: uppercase !important;
            letter-spacing: 1px !important;
            font-weight: 700 !important;
            color: #64748b !important;
            margin-bottom: 8px;
        }

        /* Modernized Sidebar Style Sheets */
        .stSidebar { background-color: #0f172a !important; }
        
        /* Fluid Interface Action Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            padding: 12px 24px !important;
            border-radius: 12px !important;
            border: none !important;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.2) !important;
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(79, 70, 229, 0.35) !important;
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
    st.markdown("""
        <div style='text-align: center; padding: 20px;'>
            <h2 style='color: #4f46e5; font-size: 40px; font-weight:900;'>Deep CSC</h2>
            <p style='color: #64748b; font-size: 16px; margin-top: -10px;'>Secure AI Gateway Verification Panel</p>
        </div>
    """, unsafe_allow_html=True)
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
# SIDEBAR NAVIGATION
# -------------------------
st.sidebar.markdown("""
    <div style='background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 15px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #334155;'>
        <h2 style='color: #38bdf8 !important; font-size: 22px; font-weight: 900; margin: 0;'>Deep CSC</h2>
        <span style='color: #94a3b8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;'>AI Tool Core Creator</span>
    </div>
""", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='color: #94a3b8; font-size: 14px;'>Active Session: <b style='color:#f8fafc;'>{USERNAME}</b></p>", unsafe_allow_html=True)
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
    st.error(f"Model Error: {e}")
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
# MODULE 1: UPLOAD & PROCESS
# -------------------------
if app_mode == "📤 Upload & Process":
    # Colorful Top Banner
    st.markdown("""
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 15px;">Automated structural data parsing pipeline powered by Gemini Vision Core.</p>
            </div>
            <div class="branding-badge">Engineered by Deep CSC</div>
        </div>
    """, unsafe_allow_html=True)
    
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
                        prompt = """
                        Analyze this bill image carefully.
                        Extract:
                        - shop_name
                        - bill_date
                        - gst_number
                        - items
                        - total

                        Return ONLY valid JSON format mapping the structure below. Do not output anything except pure JSON code block.
                        {
                          "shop_name":"",
                          "bill_date":"",
                          "gst_number":"",
                          "items":[
                            { "name":"", "qty":"", "rate":"", "amount":"" }
                          ],
                          "total":""
                        }
                        """
                        
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
                                        st.warning(f"⏳ Rate Limit hit! Auto-retrying step in {retry_delay}s... (Cycle {attempt + 1}/{max_retries})")
                                        time.sleep(retry_delay)
                                        retry_delay *= 2
                                    else:
                                        st.error("❌ Quota Exhausted! Switch to Pay-As-You-Go plan on Google AI Studio.")
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
                                x1.metric("Summation of Extracted Items", f"₹{calculated_total:,.2f}")
                                x2.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")
                                
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
                                    message = f"🧾 *AI Bill Alert*\\nShop: {shop_name}\\nDate: {bill_date}\\nTotal: ₹{bill_total}\\nStatus: {status_txt}"
                                    wa_url = "https://wa.me/?text=" + urllib.parse.quote(message)
                                    st.link_button("📱 Forward Summary to WhatsApp", wa_url, use_container_width=True)
                                    
                            except Exception as parse_err:
                                st.error(f"Structural Parsing Fault: {str(parse_err)}")

# -------------------------
# MODULE 2: DASHBOARD & HISTORY
# -------------------------
elif app_mode == "📊 Dashboard & History":
    # Colorful Top Banner Custom Designed for Creator Deep CSC
    st.markdown("""
        <div class="deep-csc-header" style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);">
            <div class="branding-text">
                <h1 style="background: linear-gradient(to right, #38bdf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">📊 Financial Operations Command Center</h1>
                <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 15px;">Real-time telemetry, advanced ledger tracking, and algorithmic auditing metrics logs.</p>
            </div>
            <div class="branding-badge" style="background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); box-shadow: 0 4px 12px rgba(236, 72, 153, 0.3);">Created by Deep CSC</div>
        </div>
    """, unsafe_allow_html=True)
    
    conn = sqlite3.connect("bills.db")
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()
    
    if df_db.empty:
        st.markdown("""
            <div style="background-color: #eff6ff; border-left: 5px solid #3b82f6; padding: 20px; border-radius: 8px; margin-top:20px;">
                <h4 style="color: #1e40af !important; margin:0 0 8px 0;">ℹ️ System Logs Empty</h4>
                <p style="color: #1e3a8a; margin:0; font-size:14px;">Dashboard active hone ke liye data ka hona zaroori hai. Kripya pehle <b>'📥 Upload & Process'</b> section mein jaakar koi bhi bill process kijiye, phir yahan real-time metrics, colorful graphics aur database automatically update ho jayenge!</p>
            </div>
        """, unsafe_allow_html=True)
    else:
        total_spent = df_db["total"].sum()
        total_invoices = len(df_db)
        mismatched_count = len(df_db[df_db["status"] == "Mismatch"])
        
        # Colorful Indicated CSS Columns for Metrics
        st.markdown("<div style='margin-bottom: -10px;'></div>", unsafe_allow_html=True)
        db1, db2, db3 = st.columns(3, gap="large")
        
        with db1:
            st.markdown("<style>div[data-testid='stMetric'] { border-top: 6px solid #4f46e5 !important; }</style>", unsafe_allow_html=True)
            st.metric("💰 Aggregate Pipeline Spend", f"₹{total_spent:,.2f}")
        with db2:
            st.markdown("<style>div[data-testid='stMetric'] { border-top: 6px solid #10b981 !important; }</style>", unsafe_allow_html=True)
            st.metric("📄 Corporate Vouchers Audited", f"{total_invoices} Bills")
        with db3:
            if mismatched_count > 0:
                st.markdown("<style>div[data-testid='stMetric'] { border-top: 6px solid #ef4444 !important; }</style>", unsafe_allow_html=True)
                st.metric("⚠️ Failed Integrity Mismatches", f"{mismatched_count} Issues")
            else:
                st.markdown("<style>div[data-testid='stMetric'] { border-top: 6px solid #06b6d4 !important; }</style>", unsafe_allow_html=True)
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
