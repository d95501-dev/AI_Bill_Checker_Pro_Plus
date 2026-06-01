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

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(
    page_title="AI Bill Checker Pro",
    page_icon="🧾",
    layout="wide"
)

# -------------------------
# DATABASE SETUP
# -------------------------
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    # Table for main bill info
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
    # Duplicate Check
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
# Default fallback values safely handled
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
st.sidebar.success(f"Logged In as: {USERNAME}")
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

if st.sidebar.button("🚪 Logout"):
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
    
    # Enabled Multi-upload feature
    uploaded_files = st.file_uploader(
        "Upload Bill Images (Multiple Allowed)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            st.markdown(f"---")
            st.subheader(f"📄 Processing Item [{idx+1}]: {file.name}")
            
            image = Image.open(file)
            col_img, col_act = st.columns([1, 2])
            
            with col_img:
                st.image(image, caption=file.name, use_container_width=True)
                
            with col_act:
                if st.button(f"🔍 Analyze {file.name}", key=f"btn_{idx}"):
                    with st.spinner("Gemini AI is parsing structural data..."):
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
                            
                            # Layout presentation
                            st.markdown(f"### 🏪 parsed: **{shop_name}**")
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Date String", bill_date)
                            
                            # GST Verification logic
                            is_valid_gst, formatted_gst = validate_gst(gst_number)
                            if gst_number != "N/A" and is_valid_gst:
                                c2.success(f"✅ GST Valid: {formatted_gst}")
                            elif gst_number != "N/A":
                                c2.warning(f"⚠️ Invalid GST Format: {gst_number}")
                            else:
                                c2.info("GST Not Found")
                                
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
                                
                            # Total validation logic
                            diff = abs(calculated_total - bill_total)
                            status_txt = "Matched" if diff < 1 else "Mismatch"
                            
                            x1, x2 = st.columns(2)
                            x1.metric("Calculated Cumulative Total", f"₹{calculated_total:,.2f}")
                            x2.metric("Declared Invoice Total", f"₹{bill_total:,.2f}")
                            
                            if status_txt == "Matched":
                                st.success("✅ Auto-Arithmetic Check Pass: Bill Total Matched.")
                            else:
                                st.error(f"❌ Verification Warning: Calculation mismatch of ₹{diff:,.2f}")
                                
                            # Save to SQLite Database with Duplicate Checks
                            saved, db_msg = insert_bill(shop_name, bill_date, gst_number, bill_total, calculated_total, status_txt)
                            if saved:
                                st.success(f"💾 Record committed to database: {db_msg}")
                            else:
                                st.warning(f"🚨 Operational Skip: {db_msg}")
                                
                            # -------------------------
                            # EXPORTS & UTILITIES
                            # -------------------------
                            st.markdown("#### Actions & Exports")
                            excel_buffer = BytesIO()
                            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                                pd.DataFrame(items).to_excel(writer, index=False, sheet_name="Items Output")
                                
                            # PDF Document Generation setup
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
                            
                            # Action Row Buttons
                            ut1, ut2, ut3 = st.columns(3)
                            with ut1:
                                st.download_button("📥 Download Excel Data", data=excel_buffer.getvalue(), file_name=f"{shop_name}_report.xlsx", mime="application/vnd.ms-excel")
                            with ut2:
                                with open(pdf_temp.name, "rb") as f:
                                    st.download_button("📄 Download PDF Summary", f.read(), file_name=f"{shop_name}_invoice.pdf", mime="application/pdf")
                            with ut3:
                                message = f"🧾 *AI Bill Alert*\nShop: {shop_name}\nDate: {bill_date}\nTotal: ₹{bill_total}\nStatus: {status_txt}"
                                wa_url = "https://wa.me/?text=" + urllib.parse.quote(message)
                                st.link_button("📱 Forward to WhatsApp", wa_url)
                                
                        except Exception as parse_err:
                            st.error(f"Engine Core Error processing structural block: {str(parse_err)}")

# -------------------------
# MODULE 2: DASHBOARD & HISTORY
# -------------------------
elif app_mode == "📊 Dashboard & History":
    st.title("📊 System Analytics & Operational DB Logs")
    
    conn = sqlite3.connect("bills.db")
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()
    
    if df_db.empty:
        st.info("Database is empty. Please upload invoices to view metrics dashboard visualization elements.")
    else:
        # Dynamic calculation metrics cards
        total_spent = df_db["total"].sum()
        total_invoices = len(df_db)
        mismatched_count = len(df_db[df_db["status"] == "Mismatch"])
        
        db1, db2, db3 = st.columns(3)
        db1.metric("Aggregated Gross Spend", f"₹{total_spent:,.2f}")
        db2.metric("Invoices Processed", total_invoices)
        db3.metric("Mismatched Verification Audits", mismatched_count, delta_color="inverse")
        
        # Simple analytic visualization chart pipeline
        st.markdown("### 📈 Vendor Distribution Trends")
        chart_data = df_db.groupby("shop_name")["total"].sum().sort_values(ascending=False)
        st.bar_chart(chart_data)
        
        # Historical search filters layout UI
        st.markdown("### 🔍 Search & Audit Registry Logs")
        search_query = st.text_input("Filter registry logs by Shop Name / Vendor keyword matches")
        
        filtered_df = df_db
        if search_query:
            filtered_df = df_db[df_db["shop_name"].str.contains(search_query, case=False, na=False)]
            
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
