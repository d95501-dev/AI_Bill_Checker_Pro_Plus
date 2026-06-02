import streamlit as st
import platform
import os

# --- Page Config ---
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# --- 1. Session State Initialization ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# --- 2. Login Logic ---
if not st.session_state.logged_in:
    st.title("🔐 System Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        # Yahan apni hardcoded ID/Password rakhein
        if username == "admin" and password == "admin":
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Login")
    st.stop() # Login hone tak aage ka code nahi chalega

# --- 3. Main App Logic (Sirf Logged-in users ke liye) ---
st.title("🧾 AI Multi-Bill OCR Processor")

# Hardware Module (Cloud Safe)
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    col1, col2 = st.columns(2)
    
    with col1:
        # Check if running on Windows (Local PC)
        if platform.system() == "Windows":
            if st.button("🚀 Open Brother iPrint&Scan"):
                try:
                    os.startfile(r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe")
                except Exception as e:
                    st.error(f"Path Error: {e}")
        else:
            st.info("Scanner feature is only available on your local Windows machine.")
            
    with col2:
        if st.button("🖨️ Open Print Dialog"):
            st.components.v1.html("<script>window.print();</script>", height=0)

# Sidebar Navigation
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

if app_mode == "📤 Upload & Process":
    st.header("📤 Upload & Process")
    hardware_module()
    uploaded_files = st.file_uploader("Upload Bill Images", accept_multiple_files=True)
    # Baaki processing logic yahan aayega

elif app_mode == "📊 Dashboard & History":
    st.header("📊 Dashboard & History")
    st.write("Dashboard loading...")
