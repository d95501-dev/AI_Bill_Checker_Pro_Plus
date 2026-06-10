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
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

# --- CORE FUNCTIONS ---
def safe_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0

def normalize_items(items):
    if not isinstance(items, list): return []
    return [{"name": it.get("name") or "", "qty": it.get("qty") or "", 
             "rate": it.get("rate") or "", "amount": it.get("amount") or ""} for it in items]

# --- PREMIUM EXCEL GENERATOR (Audit Style) ---
def build_excel_export(results):
    buffer = BytesIO()
    wb = openpyxl.Workbook()
    
    # 1. Summary Dashboard Tab
    ws_summary = wb.active
    ws_summary.title = "Summary Dashboard"
    
    headers = ["Bill No.", "Bill Date", "Reported Total (₹)", "Calculated Total (₹)", "Discrepancy (₹)", "Status / Notes"]
    for col_idx, text in enumerate(headers, 1):
        ws_summary.cell(row=1, column=col_idx, value=text).font = Font(bold=True)
        ws_summary.column_dimensions[get_column_letter(col_idx)].width = 20

    # 2. Process Data
    for idx, item in enumerate(results, start=2):
        d = item.get("data") or {}
        items = normalize_items(d.get("items"))
        bill_total = safe_float(d.get("total", 0))
        calc_total = sum(safe_float(it.get("amount", 0)) for it in items)
        diff = bill_total - calc_total
        
        status = "Verified / Match" if abs(diff) < 1 else f"Mismatch: {diff:+.1f}"
        
        # Write Summary
        ws_summary.cell(row=idx, column=1, value=f"1{idx+90}") # Example Bill No logic
        ws_summary.cell(row=idx, column=2, value=str(d.get("bill_date", "N/A")))
        ws_summary.cell(row=idx, column=3, value=bill_total)
        ws_summary.cell(row=idx, column=4, value=calc_total)
        ws_summary.cell(row=idx, column=5, value=diff)
        ws_summary.cell(row=idx, column=6, value=status)
        
        # 3. Detailed Line Items Tab
        ws_detail = wb.create_sheet(title=f"Bill_{1090+idx}")
        ws_detail["A1"] = "GEETA FRUIT & VEGETABLES SUPPLIERS - DETAILED BILLING TRANSACTIONS"
        ws_detail.merge_cells('A1:D1')
        
        item_headers = ["Particulars (Items)", "Quantity", "Rate (₹)", "Amount (₹)"]
        for c_idx, h in enumerate(item_headers, 1):
            ws_detail.cell(row=3, column=c_idx, value=h).font = Font(bold=True)
            
        for r_idx, it in enumerate(items, 4):
            ws_detail.cell(row=r_idx, column=1, value=it.get("name"))
            ws_detail.cell(row=r_idx, column=2, value=it.get("qty"))
            ws_detail.cell(row=r_idx, column=3, value=safe_float(it.get("rate")))
            ws_detail.cell(row=r_idx, column=4, value=safe_float(it.get("amount")))

    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title="Deep CSC Audit", layout="wide")
    st.title("🧾 AI Bill Audit Processor")
    
    # Simple file uploader mock for testing
    uploaded_files = st.file_uploader("Upload Bills", accept_multiple_files=True)
    
    if st.button("Generate Audit Report"):
        # Placeholder for processed results
        results = [] # Yaha aapka logic ayega jo JSON data return karega
        
        if results:
            excel_data = build_excel_export(results)
            st.download_button(
                label="📥 Download Audit Excel",
                data=excel_data,
                file_name="Vegetable_Bill_Audit_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main()
