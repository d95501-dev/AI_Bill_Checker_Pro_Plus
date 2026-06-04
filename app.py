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

# --- Puraane zaroori functions (Inhe mat hatana) ---
def parse_json_from_response(response_text):
    raw = response_text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\[.*\]|\{.*\}", raw, re.DOTALL)
    if match: raw = match.group(0)
    return json.loads(raw)

def render_bill_result(data, source_name):
    # Yeh wahi function hai jo aapne pehle likha tha
    shop_name = data.get("shop_name", "Unknown")
    st.write(f"### Bill: {shop_name}")
    st.json(data) # Filhal ke liye test karne ko

# --- UPDATED FUNCTIONS ---

def analyze_bill(model, images):
    prompt = """
    Analyze these images. They contain one or more bills.
    Extract data and return ONLY a JSON list of objects:
    [{"shop_name": "...", "bill_date": "...", "gst_number": "...", "items": [], "total": 0}]
    No markdown, no conversation.
    """
    if not isinstance(images, list): images = [images]
    response = model.generate_content([prompt] + images)
    return parse_json_from_response(response.text)

def render_upload_module(model):
    st.subheader("📤 AI Multi-Bill OCR Processor")
    uploaded_files = st.file_uploader("Upload files", type=["jpg", "png", "pdf"], accept_multiple_files=True)

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            if st.button(f"⚡ Process {file.name}", key=f"btn_{idx}"):
                with st.spinner("Processing..."):
                    try:
                        if file.name.lower().endswith(".pdf"):
                            images = convert_from_bytes(file.read())
                        else:
                            images = [Image.open(file)]
                        
                        results = analyze_bill(model, images)
                        
                        if isinstance(results, list):
                            for bill_data in results:
                                render_bill_result(bill_data, file.name)
                        else:
                            render_bill_result(results, file.name)
                    except Exception as e:
                        st.error(f"Error: {e}")

# --- MAIN ---
def main():
    # Setup page, css, auth yahan call karein
    model = genai.GenerativeModel("gemini-2.0-flash") # Model name check karein
    render_upload_module(model)

if __name__ == "__main__":
    main()
