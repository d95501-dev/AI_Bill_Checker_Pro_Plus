import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
import sqlite3
import re
import os
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import urllib.parse

# ==========================================
# PAGE CONFIG & STYLES (Kept existing for consistency)
# ==========================================
st.set_page_config(page_title="Deep CSC AI Bill Processor", page_icon="🧾", layout="wide")

st.markdown("""
<style>
.stMetric { background: #ffffff; padding: 15px; border-radius: 10px; border-left: 5px solid #38bdf8; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# DATABASE ENHANCEMENTS
# ==========================================
def init_db():
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT, bill_date TEXT, gst_number TEXT,
            total REAL, calculated_total REAL, status TEXT, timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def delete_bill(bill_id):
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM bills WHERE id=?", (bill_id,))
    conn.commit()
    conn.close()

init_db()

# ... [Keep your insert_bill, validate_gst, and login logic here] ...

# ==========================================
# MODULE 2: DASHBOARD & HISTORY (ENHANCED)
# ==========================================
elif app_mode == "📊 Dashboard & History":
    st.markdown("## 📊 Financial Dashboard")
    
    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("No records found.")
    else:
        # Quick Actions
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Value", f"₹{df['total'].sum():,.2f}")
        col2.metric("Total Bills", len(df))
        
        # Data Table with Delete Feature
        st.subheader("📋 Ledger Records")
        edited_df = st.data_editor(
            df, 
            column_config={"id": None}, # Hide ID
            use_container_width=True
        )
        
        # Delete Selected Row
        del_col, exp_col = st.columns([1, 4])
        with del_col:
            bill_id_to_del = st.number_input("Delete Bill ID", min_value=1, step=1)
            if st.button("🗑️ Remove Entry"):
                delete_bill(bill_id_to_del)
                st.rerun()

        # Analytics
        st.subheader("📈 Insights")
        c1, c2 = st.columns(2)
        with c1: st.bar_chart(df.groupby("status")["total"].count())
        with c2: st.bar_chart(df.groupby("shop_name")["total"].sum())

# ==========================================
# NEW MODULE: ABOUT & HELP
# ==========================================
# Added a small sidebar footer to keep it professional
st.sidebar.markdown("---")
st.sidebar.info("Pro Tip: Ensure bill images are well-lit for better OCR results.")
