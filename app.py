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
        .main { background-color: #fcfdfe; }
        h1, h2, h3 { font-family: 'Inter', sans-serif; color: #0f172a !important; font-weight: 800 !important; }
        
        /* Custom Modern Metric Cards styling */
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            padding: 24px;
            border-radius: 16px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
            border: 1px solid #e2e8f0;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        }
        div[data-testid="stMetricValue"] {
            font-size: 32px !important;
            font-weight: 800 !important;
            color: #4f46e5 !important;
            letter-spacing: -0.5px;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 14px !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600 !important;
            color: #64748b !important;
            margin-bottom: 8px;
        }
        
        /* Form, Input elements and Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
            color: white !important;
            font-weight: 600 !important;
            padding: 12px 24px;
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2);
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            transform: scale(1.02);
            box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.4);
        }
        
        /* Block sections container box design */
        .block-container { padding-top: 2rem !important; }
        hr { border-top: 1px solid #e2e8f0; }
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
st.sidebar.markdown("<h2 style='font-size: 20px; margin-bottom: 0px;'>🏢 Core Admin Terminal</h2>", unsafe_allow_html=True)
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
    st.markdown("<p style='color: #64748b; font-size: 16px; margin-top:-15px;'>Automated structural data parsing pipeline powered by Gemini Vision Core.</p>", unsafe_allow_html=True)
    
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
                                    message = f"🧾 *AI Bill Alert*\nShop: {shop_name}\nDate: {bill_date}\nTotal: ₹{bill_total}\nStatus: {
