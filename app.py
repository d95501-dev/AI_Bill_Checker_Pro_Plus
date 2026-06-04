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
import os
import subprocess
import time
from pdf2image import convert_from_bytes # PDF support

# --- Configuration ---
APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"

# --- Sabhi Support Functions Yahan Honge ---
def setup_page():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

def apply_css():
    st.markdown("""<style>.main { background-color: #f8fafc; }</style>""", unsafe_allow_html=True)

def parse_json_from_response(response_text):
    try:
        raw = response_text.strip().replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
        if match: raw = match.group(0)
        return json.loads(raw)
    except: return {}

def analyze_bill(model, file_payload):
    prompt = "Extract bill details as JSON: {shop_name, bill_date, gst_number, items: [{name, qty, rate, amount}], total}. No extra text."
    # Agar list (PDF pages) hai to list bhejein
    response = model.generate_content([prompt] + (file_payload if isinstance(file_payload, list) else [file_payload]))
    return parse_json_from_response(response.text)

# --- Baki purane functions (insert_bill, render_bill_result, render_dashboard, render_hardware_module) Yahan paste karein ---

def render_upload_module(model):
    st.markdown("### 📤 AI Multi-Bill OCR Processor")
    uploaded_files = st.file_uploader("Upload Images/PDFs", type=["jpg", "png", "pdf"], accept_multiple_files=True)

    if uploaded_files:
        for file in uploaded_files:
            if st.button(f"⚡ Process {file.name}"):
                with st.spinner("Processing..."):
                    try:
                        if file.name.lower().endswith(".pdf"):
                            payload = convert_from_bytes(file.read())
                        else:
                            payload = Image.open(file)
                        
                        data = analyze_bill(model, payload)
                        render_bill_result(data, file.name)
                    except Exception as e:
                        st.error(f"Error: {e}")

# --- Main App Logic ---
def main():
    setup_page()
    apply_css()
    
    # Session State
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    
    # Model Setup
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("API Key missing in secrets!")
        return
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # App flow
    if not st.session_state.logged_in:
        do_login() # Purana login function yahan call karein
    else:
        app_mode = st.sidebar.selectbox("Navigate", ["📤 Upload & Process", "📊 Dashboard & History"])
        if app_mode == "📤 Upload & Process":
            render_upload_module(model)
            render_hardware_module()
        else:
            render_dashboard()

if __name__ == "__main__":
    main()
