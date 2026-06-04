import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from pdf2image import convert_from_bytes
import json
import re
import sqlite3

# --- 1. CONFIG & VARIABLES ---
APP_TITLE = "Deep CSC - AI Bill Processor"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "password123"

# --- 2. LOGIC FUNCTIONS ---
def parse_json(text):
    raw = text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
    if match: return json.loads(match.group(0))
    return {}

def analyze_bill(model, payload):
    prompt = "Extract details: shop_name, bill_date, gst, total, items. Return ONLY JSON."
    response = model.generate_content([prompt] + (payload if isinstance(payload, list) else [payload]))
    return parse_json(response.text)

# --- 3. UI FUNCTIONS ---
def do_login():
    st.title("🔐 System Login")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if user == DEFAULT_USERNAME and pwd == DEFAULT_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid Credentials")
    st.stop() # Login hone tak aage ka code nahi chalega

def render_upload_module(model):
    st.subheader("📤 PDF/Image Processor")
    files = st.file_uploader("Upload", type=["jpg", "png", "pdf"], accept_multiple_files=True)
    if files:
        for file in files:
            if st.button(f"Process {file.name}"):
                payload = convert_from_bytes(file.read()) if file.name.endswith(".pdf") else Image.open(file)
                data = analyze_bill(model, payload)
                st.json(data)

# --- 4. MAIN ---
def main():
    st.set_page_config(page_title=APP_TITLE)
    
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        do_login() # Ye function ab defined hai
    
    # Login ke baad ka part
    api_key = st.secrets.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    st.sidebar.title("Menu")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
        
    render_upload_module(model)

if __name__ == "__main__":
    main()
