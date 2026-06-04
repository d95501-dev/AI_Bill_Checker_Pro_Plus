import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from pdf2image import convert_from_bytes
import json
import re
import sqlite3
import os
import tempfile
import time

# --- CONSTANTS & CONFIG ---
APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "password123"

# --- SETUP PAGE ---
def setup_page():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

# --- DATABASE & HELPERS ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)")
    conn.commit()
    conn.close()

def parse_json_from_response(response_text):
    raw = response_text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\[.*\]|\{.*\}", raw, re.DOTALL)
    if match: return json.loads(match.group(0))
    return {}

# --- AI LOGIC ---
def analyze_bill(model, input_data):
    prompt = "Extract bill details as JSON list of objects: {shop_name, bill_date, gst_number, items, total}. No extra text."
    response = model.generate_content([prompt] + (input_data if isinstance(input_data, list) else [input_data]))
    return parse_json_from_response(response.text)

# --- UI FUNCTIONS ---
def do_login():
    st.title("🔐 System Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Credentials")
    st.stop()

def render_upload_module(model):
    st.subheader("📤 AI Multi-Bill OCR Processor")
    uploaded_files = st.file_uploader("Upload Images/PDFs", type=["jpg", "png", "pdf"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            if st.button(f"⚡ Process {file.name}"):
                with st.spinner("Analyzing..."):
                    try:
                        payload = convert_from_bytes(file.read()) if file.name.lower().endswith(".pdf") else Image.open(file)
                        data = analyze_bill(model, payload)
                        st.json(data) # Show result
                    except Exception as e:
                        st.error(f"Error: {e}")

# --- MAIN APP ---
def main():
    setup_page()
    init_db()
    
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in:
        do_login()
    
    # Configure Gemini
    api_key = st.secrets.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Sidebar Navigation
    app_mode = st.sidebar.selectbox("Navigate", ["📤 Upload & Process", "📊 Dashboard"])
    if app_mode == "📤 Upload & Process":
        render_upload_module(model)
    else:
        st.write("📊 Dashboard Under Construction")

if __name__ == "__main__":
    main()
