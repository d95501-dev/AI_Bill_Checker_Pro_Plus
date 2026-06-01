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
    page_title="AI Bill Checker Pro+",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Enterprise Styling Injection
st.markdown("""
    <style>
        /* Global CSS Overrides */
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #4F46E5; }
        div[data-testid="stMetricValue"] { font-size: 24px; font-weight: 700; color: #1E293B; }
        div[data-testid="stMetricLabel"] { font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748B; }
        .stButton>button { border-radius: 6px; font-weight: 500; transition: all 0.3s ease; }
        .stButton>button:hover { transform: translateY(-1px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
""", unsafe_allow_html=True) # <-- Isko "unsafe_allow_html=True" kar dein

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
st.sidebar.markdown("### 🏢 Core Admin Terminal")
st.sidebar.success(f"Active User: {USERNAME}")
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Logout System", use_container_width=True):
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
    st.title("🧾 AI Multi-Bill OCR Processor")
    st.markdown("Automated structural data parsing pipeline powered by Gemini Vision Core.")
    
    uploaded_files = st.file_uploader(
        "Drop batch bill images below (Multi-upload supported)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            st.markdown(f"---")
            st.subheader(f"📄 Processing Block [{idx+1}]: {file.name}")
            
            image = Image.open(file)
            col_img, col_act = st.columns([1, 2], gap="large")
            
            with col_img:
                st.image(image, caption=f"Source: {file.name}", use_container_width=True)
                
            with col_act:
                if st.button(f"⚡ Execute AI Analysis", key=f"btn_{idx}", use_container_width=True, type="primary"):
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
                                    st.markdown("#### Detailed Line-Item Breakdown")
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
                                
                                st.markdown("#### Arithmetic Audit Engine")
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
                                    message = f"🧾 *AI Bill Alert*\nShop: {shop_name}\nDate: {bill_date}\nTotal: ₹{bill_total}\nStatus: {status_txt}"
                                    wa_url = "https://wa.me/?text=" + urllib.parse.quote(message)
                                    st.link_button("📱 Forward Summary to WhatsApp", wa_url, use_container_width=True)
                                    
                            except Exception as parse_err:
                                st.error(f"Structural Parsing Fault: {str(parse_err)}")

# -------------------------
# MODULE 2: DASHBOARD & HISTORY (PROFESSIONAL UPGRADE)
# -------------------------
elif app_mode == "📊 Dashboard & History":
    st.title("📊 Financial Operations Command Center")
    st.markdown("Real-time telemetry, duplicate transaction logs, and ledger integrity checks.")
    
    conn = sqlite3.connect("bills.db")
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()
    
    if df_db.empty:
        st.info("System Engine reporting zero active logs. Process incoming invoices to unlock dashboard diagnostics.")
    else:
        # KPI Engineering Panel
        total_spent = df_db["total"].sum()
        total_invoices = len(df_db)
        mismatched_count = len(df_db[df_db["status"] == "Mismatch"])
        
        db1, db2, db3 = st.columns(3)
        db1.metric("💰 Aggregate Pipeline Spend", f"₹{total_spent:,.2f}")
        db2.metric("📄 Corporate Vouchers Audited", f"{total_invoices} Invoices")
        
        # Color coding metrics manually using delta-color contextual mapping
        if mismatched_count > 0:
            db3.metric("⚠️ Failed Integrity Mismatches", f"{mismatched_count} Incidents")
        else:
            db3.metric("✅ System Integrity Audit", "100% Cleared")
            
        st.markdown("---")
        
        # Advanced Multi-View Analytics Engine Block
        st.markdown("### 📈 Visual Intelligence Analytics")
        graph_col1, graph_col2 = st.columns([2, 1], gap="large")
        
        with graph_col1:
            st.markdown("**Vendor Distribution Analytics (Gross Allocation Value)**")
            chart_data = df_db.groupby("shop_name")["total"].sum().reset_index().sort_values(by="total", ascending=False).head(8)
            chart_data = chart_data.set_index("shop_name")
            st.bar_chart(chart_data, y="total", color="#4F46E5")
            
        with graph_col2:
            st.markdown("**Ledger Status Audit Breakdown**")
            status_distribution = df_db["status"].value_counts().reset_index()
            status_distribution.columns = ["Audit Status", "Volume Counter"]
            st.dataframe(status_distribution, use_container_width=True, hide_index=True)
            
        st.markdown("---")
        
        # Dynamic Search, Controls & Registry Audit Logging
        st.markdown("### 🔍 Centralized Ledger Records Registry")
        
        query_col, export_col = st.columns([3, 1], gap="medium")
        with query_col:
            search_query = st.text_input("⚡ Smart Filter (Input target Vendor Name / Retail Shop keyword string)")
        with export_col:
            st.markdown("<div style='height:28px;'></div>", unsafe_style_html=True)
            master_excel_buffer = BytesIO()
            with pd.ExcelWriter(master_excel_buffer, engine="openpyxl") as writer:
                df_db.to_excel(writer, index=False, sheet_name="Master DB Sheet")
            st.download_button("📥 Master Export DB Logs", data=master_excel_buffer.getvalue(), file_name="Corporate_Master_Ledger.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            
        filtered_df = df_db
        if search_query:
            filtered_df = df_db[df_db["shop_name"].str.contains(search_query, case=False, na=False)]
            
        # Clean formatting for presentation layer data tables
        display_df = filtered_df.copy()
        display_df.columns = ["Log ID", "Vendor Station", "Invoice Date", "Registered GSTIN", "Invoice Cost (₹)", "Computed Cost (₹)", "Audit Evaluation", "System Timestamp"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
