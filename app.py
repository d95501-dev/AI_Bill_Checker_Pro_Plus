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
# PAGE CONFIG & CSS (ORIGINAL PREMIUM LOOK)
# -------------------------
st.set_page_config(page_title="Deep CSC - AI Bill Processor", page_icon="🧾", layout="wide")

st.markdown("""
    <style>
        .main { background-color: #f8fafc; }
        .deep-csc-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            padding: 30px; border-radius: 24px; margin-bottom: 35px;
            color: white;
        }
        .branding-text h1 { color: #38bdf8 !important; }
        div[data-testid="stMetric"] { background: #ffffff; padding: 24px; border-radius: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .stSidebar { background-color: #0f172a !important; color: white; }
    </style>
""", unsafe_allow_html=True)

# -------------------------
# DATABASE & HELPERS
# -------------------------
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_name TEXT, bill_date TEXT, gst_number TEXT, total REAL, calculated_total REAL, status TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# -------------------------
# MAIN APP
# -------------------------
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

if app_mode == "📤 Upload & Process":
    st.markdown('<div class="deep-csc-header"><h1>🧾 AI Multi-Bill OCR Processor</h1></div>', unsafe_allow_html=True)
    
    # Scanner/Printer logic
    with st.expander("🖨️ Hardware Controller"):
        if st.button("🚀 Trigger Scan"): st.success("Scan Initialized...")
        if st.button("🖨️ Print Report"): st.components.v1.html("<script>window.print();</script>", height=0)

    uploaded_files = st.file_uploader("Upload Bills", accept_multiple_files=True)
    # ... (Rest of your processing logic)

elif app_mode == "📊 Dashboard & History":
    st.markdown('<div class="deep-csc-header"><h1>📊 Financial Operations Command Center</h1></div>', unsafe_allow_html=True)
    
    conn = sqlite3.connect("bills.db")
    df_db = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()

    if not df_db.empty:
        # Metrics Cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Spend", f"₹{df_db['total'].sum():,.2f}")
        col2.metric("Bills Audited", len(df_db))
        col3.metric("Status", "Operational")

        # Charts
        st.subheader("📈 Top Vendors Distribution")
        chart_data = df_db.groupby("shop_name")["total"].sum()
        st.bar_chart(chart_data)

        # Full Table
        st.dataframe(df_db, use_container_width=True)
    else:
        st.info("No data available yet. Process some bills first!")
