import streamlit as st
import platform
import os

# --- Page Config ---
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# --- Session Management ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# --- Login Logic ---
if not st.session_state.logged_in:
    st.title("🔐 System Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == "admin" and password == "admin":
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Login")
    st.stop()

# --- Main App ---
st.title("🧾 AI Multi-Bill OCR Processor")

# Navigation
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

# Scanner Function (Safe for Cloud & Windows)
def run_scanner():
    if platform.system() == "Windows":
        try:
            # Ye path sirf tabhi chalega jab aap apni local machine par honge
            os.startfile(r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe")
            st.success("Scanner launching...")
        except Exception as e:
            st.error(f"Scanner not found: {e}")
    else:
        st.warning("Scanner feature is only for Local Windows PC.")

# Interface
if app_mode == "📤 Upload & Process":
    st.header("📤 Upload & Process")
    
    with st.expander("🖨️ Hardware Controller", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Open Scanner"):
                run_scanner()
        with col2:
            if st.button("🖨️ Print Page"):
                st.components.v1.html("<script>window.print();</script>", height=0)
    
    st.file_uploader("Upload Bills", accept_multiple_files=True)

elif app_mode == "📊 Dashboard & History":
    st.header("📊 Dashboard")
    st.info("Dashboard module is currently under maintenance.")
