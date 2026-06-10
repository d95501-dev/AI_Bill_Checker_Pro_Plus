import base64
import json
import os
import re
import sqlite3
from datetime import datetime
from io import BytesIO
import pandas as pd
import streamlit as st
from PIL import Image
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side

# --- CONFIG ---
APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"

# --- DATABASE INIT ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_name TEXT, bill_date TEXT, gst_number TEXT,
                total REAL, calculated_total REAL, status TEXT, timestamp TEXT
            )
        """)

# --- NEW EXCEL EXPORT (YOUR REQUIREMENT) ---
def build_excel_export(results):
    buffer = BytesIO()
    wb = openpyxl.Workbook()
    
    # 1. Summary Dashboard Sheet
    ws1 = wb.active
    ws1.title = "Summary Dashboard"
    ws1.append(["Bill No.", "Bill Date", "Reported Total (₹)", "Calculated Total (₹)", "Discrepancy (₹)", "Status / Notes"])
    
    # 2. Detailed Line Items Sheet
    ws2 = wb.create_sheet(title="Detailed Line Items")
    ws2.append(["Bill No.", "Date", "Particulars (Items)", "Quantity", "Rate (₹)", "Amount (₹)"])

    for idx, item in enumerate(results, start=1):
        d = item.get("data", {})
        bill_no = d.get("bill_no", f"Bill_{idx}")
        bill_date = d.get("bill_date", "N/A")
        total = float(str(d.get("total", 0)).replace(',', ''))
        items = d.get("items", [])
        
        calc_total = sum(float(str(i.get("amount", 0)).replace(',', '')) for i in items)
        diff = total - calc_total
        status = "Verified / Match" if abs(diff) < 1 else "Mismatch"
        
        ws1.append([bill_no, bill_date, total, calc_total, diff, status])
        for it in items:
            ws2.append([bill_no, bill_date, it.get("name", ""), it.get("qty", ""), 
                        float(str(it.get("rate", 0)).replace(',', '')), 
                        float(str(it.get("amount", 0)).replace(',', ''))])
            
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- DASHBOARD UI ---
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_db()
    
    st.title("🧾 Deep CSC - AI Bill Processor")
    
    # Ye wahi tabs hain jo aapke purane dashboard mein the
    tabs = st.tabs(["Processor", "Dashboard", "Settings"])
    
    with tabs[1]:
        st.subheader("Bill History Dashboard")
        with sqlite3.connect(DB_PATH) as conn:
            try:
                # Purana UI layout query
                query = "SELECT shop_name, bill_date, gst_number, total, calculated_total, status, timestamp FROM bills ORDER BY id DESC"
                df = pd.read_sql_query(query, conn)
                if not df.empty:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No records found.")
            except Exception as e:
                st.error("Database table nahi mil rahi. Pehle bills process karein.")

    # Yahan Processor logic (Tabs[0]) aayega
    with tabs[0]:
        st.write("Upload your bills here...")
        # (Aapka baki purana code yahan continue karein)

if __name__ == "__main__":
    main()
