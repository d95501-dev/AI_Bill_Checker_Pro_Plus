import streamlit as st
import platform
import os
import sqlite3
import pandas as pd

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Login Check
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 System Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == "admin" and password == "password123":
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Login")
    st.stop()

# --- AGAR LOGIN HAI TOH YE CHALEGA ---

# Hardware Module (Cloud Safe)
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    if platform.system() == "Windows":
        if st.button("🚀 Trigger Flatbed Scan"):
            try:
                os.startfile(r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe")
            except Exception as e:
                st.error(f"Path Error: {e}")
    else:
        st.info("Scanner is only available on Local Windows Desktop.")
    
    if st.button("🖨️ Send to Printer"):
        st.components.v1.html("<script>window.print();</script>", height=0)

# Sidebar Navigation
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

if app_mode == "📤 Upload & Process":
    st.header("📤 Upload & Process")
    hardware_module()
    uploaded_files = st.file_uploader("Upload Bills", accept_multiple_files=True)
    # Baaki processing logic yahan aayega...

elif app_mode == "📊 Dashboard & History":
    st.header("📊 Dashboard & History")
    # Dashboard logic yahan aayega...
