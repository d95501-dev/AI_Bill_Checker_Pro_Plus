import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
import json
import re
import subprocess

# पेज कॉन्फ़िगरेशन
st.set_page_config(page_title="Deep CSC - AI Bill Processor", page_icon="🧾", layout="wide")

# API कॉन्फ़िगरेशन
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
except Exception:
    st.error("GEMINI_API_KEY not found in Streamlit Secrets.")
    st.stop()

# Hardware Module Function
def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        col_scan, col_print = st.columns(2)
        with col_scan:
            st.markdown("#### 📷 Brother Scanner Interface")
            scan_dpi = st.select_slider("Select Resolution (DPI)", options=[150, 300, 600], value=300)
            scan_mode = st.radio("Mode", ["Color", "Grayscale", "Black & White"], horizontal=True)
            if st.button("🚀 Open Brother Scanner"):
                possible_paths = [
                    r"C:\Program Files\Brother\iPrint&Scan\BrCtrlCntr.exe",
                    r"C:\Program Files (x86)\Brother\iPrint&Scan\BrCtrlCntr.exe"
                ]
                launched = False
                for path in possible_paths:
                    try:
                        subprocess.Popen(path)
                        launched = True
                        break
                    except: pass
                if launched: st.success(f"Brother Scanner Opened ({scan_dpi} DPI - {scan_mode})")
                else: st.error("Brother iPrint&Scan software not found.")
        with col_print:
            st.markdown("#### 🖨️ Printer Interface")
            printer_name = st.selectbox("Select Printer", ["Brother DCP-T820DW", "Default System Printer"])
            copies = st.number_input("Number of Copies", min_value=1, value=1)
            if st.button("🖨️ Print Current Page"):
                st.components.v1.html("<script>window.print();</script>", height=0)
                st.success(f"Print request sent ({copies} copies)")

# मेन ऐप लेआउट
st.title("🧾 Deep CSC - AI Bill Processor")

# Sidebar navigation
app_mode = st.sidebar.selectbox("Navigate System", ["📤 Upload & Process", "Dashboard"])

if app_mode == "📤 Upload & Process":
    # यहाँ हार्डवेयर मॉड्यूल कॉल किया
    hardware_module()
    
    st.markdown("---")
    uploaded_files = st.file_uploader("Drop batch bill images below (Multi-upload supported)", type=["jpg","jpeg","png"], accept_multiple_files=True)
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            image = Image.open(uploaded_file)
            st.image(image, caption=f"Processing: {uploaded_file.name}", use_container_width=True)
            
            if st.button(f"🔍 Analyze {uploaded_file.name}"):
                with st.spinner("Analyzing..."):
                    prompt = 'Extract items (name, qty, rate, amount) and total. Return JSON only: {"items":[{"name":"","qty":"","rate":"","amount":""}], "total":""}'
                    try:
                        response = model.generate_content([prompt, image])
                        text = response.text.replace("```json", "").replace("```", "")
                        data = json.loads(text)
                        
                        df = pd.DataFrame(data.get("items", []))
                        st.dataframe(df, use_container_width=True)
                        st.metric("Total", f"₹{data.get('total', 0)}")
                    except Exception as e:
                        st.error(f"Error: {e}")

elif app_mode == "Dashboard":
    st.subheader("System Overview")
    st.write("Welcome to your Deep CSC Dashboard.")
