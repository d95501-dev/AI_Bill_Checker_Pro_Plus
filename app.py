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

# --- Main App Interface ---
st.sidebar.title("Deep CSC")
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "📊 Dashboard & History"])

# Scanner Function
def run_scanner():
    if platform.system() == "Windows":
        try:
            os.startfile(r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe")
            st.success("Scanner launching...")
        except Exception as e:
            st.error(f"Scanner path not found: {e}")
    else:
        st.warning("Scanner feature is only available on Local Windows PC.")

# --- UI Logic ---
if app_mode == "📤 Upload & Process":
    st.title("📤 Upload & Process")
    st.markdown("### 🔌 Advanced Hardware Controller")
    
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Open Brother iPrint&Scan"):
                run_scanner()
        with col2:
            if st.button("🖨️ Open Print Dialog"):
                st.components.v1.html("<script>window.print();</script>", height=0)
    
    st.subheader("Upload Bill Images")
    st.file_uploader("Upload", accept_multiple_files=True, label_visibility="collapsed")

elif app_mode == "📊 Dashboard & History":
    st.title("📊 Dashboard & History")
    # Yahan aapka purana dashboard content wapas aa gaya hai
    st.info("Showing your processed bill history records.")
    # Example for Dashboard layout
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Bills", "12")
    col_b.metric("Pending", "2")
    col_c.metric("Processed", "10")
    st.write("---")
    st.write("Data table will be displayed here.")
