import streamlit as st
import platform
import os

# --- Page Config ---
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# --- 1. Login System (Must be at the top) ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 System Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        # Yahan credentials check karein
        if username == "admin" and password == "password123":
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Login")
    st.stop() # Login hone tak niche ka code load nahi hoga

# --- 2. Main App (Sirf logged-in users ke liye) ---
st.title("🧾 AI Multi-Bill OCR Processor")

# Hardware Module (Cloud Safe)
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console"):
        col1, col2 = st.columns(2)
        with col1:
            if platform.system() == "Windows":
                if st.button("🚀 Open Brother iPrint&Scan"):
                    try:
                        os.startfile(r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe")
                    except Exception as e:
                        st.error(f"Path Error: {e}")
            else:
                st.warning("Scanner control is only for Local Windows.")
        with col2:
            if st.button("🖨️ Open Print Dialog"):
                st.components.v1.html("<script>window.print();</script>", height=0)

# Sidebar Navigation
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

if app_mode == "📤 Upload & Process":
    hardware_module()
    uploaded_files = st.file_uploader("Upload Bill Images", accept_multiple_files=True)
    if uploaded_files:
        st.success(f"{len(uploaded_files)} files uploaded.")
        
elif app_mode == "📊 Dashboard & History":
    st.header("📊 Dashboard")
    st.write("History data will appear here.")
