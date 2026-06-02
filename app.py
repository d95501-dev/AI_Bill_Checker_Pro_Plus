import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
import platform # Added for environment checking
import sqlite3
import time
import re
import urllib.parse
import tempfile
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- 1. INITIALIZE APP STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "📤 Upload & Process"

# --- 2. HARDWARE MODULE ---
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        with col_scan:
            st.markdown("#### 📷 Scanner Interface")
            # ... your existing scanner UI code ...
            if st.button("🚀 Trigger Flatbed Scan"):
                st.info("Scanner initialized...")
        with col_print:
            st.markdown("#### 🖨️ Printer Interface")
            # ... your existing printer UI code ...
            if st.button("🖨️ Send to Printer"):
                st.info("Sending to printer...")

# --- 3. MAIN NAVIGATION ---
# Set the sidebar navigation and capture the mode in session_state
st.session_state.app_mode = st.sidebar.selectbox(
    "Navigate System", 
    ["📤 Upload & Process", "📊 Dashboard & History"],
    index=0 if st.session_state.app_mode == "📤 Upload & Process" else 1
)

app_mode = st.session_state.app_mode

# --- 4. CONDITIONAL HARDWARE EXECUTION ---
if app_mode == "📤 Upload & Process":
    # ... [Insert your Upload Header code here] ...
    
    # Only show hardware controls if running on Windows (Local)
    if platform.system() == "Windows":
        hardware_module()
    else:
        st.sidebar.warning("Hardware control disabled: Running in Cloud environment.")

# ... [Rest of your logic for Upload & Process and Dashboard] ...
