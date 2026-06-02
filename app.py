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
import subprocess  # <--- Ye import hona bahut zaroori hai

# -------------------------
# PAGE CONFIG & BRANDING (Baaki ka code waisa hi rahega)
# -------------------------
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# ... (CSS Styles, init_db, insert_bill, login functions yahan par pehle jaise hi rahenge) ...

# -------------------------
# HARDWARE MODULE (Ye updated part hai)
# -------------------------
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        
        with col_scan:
            st.markdown("#### 📷 Scanner Interface")
            
            if st.button("🖼️ Open Brother iPrint&Scan"):
                try:
                    subprocess.Popen([r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe"])
                    st.success("Brother App Launching...")
                except Exception as e:
                    st.error(f"Brother App Error: {e}")
            
            if st.button("🚀 Open NAPS2 (Fast Scan)"):
                try:
                    subprocess.Popen([r"C:\Program Files\NAPS2\NAPS2.exe"])
                    st.success("NAPS2 Launching...")
                except Exception as e:
                    st.error(f"NAPS2 Error: {e}")
                    
        with col_print:
            st.markdown("#### 🖨️ Printer Interface")
            if st.button("🖨️ Open Print Dialog"):
                st.components.v1.html("<script>window.print();</script>", height=0)
                st.info("Browser Print ready.")

# -------------------------
# MAIN APP FLOW
# -------------------------
# ... (Baaki saara logic waisa hi rahega) ...

if app_mode == "📤 Upload & Process":
    # ... (Header code) ...
    
    # Yahan function call karein
    hardware_module() 
    
    # ... (Baaki processing code) ...
