import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from pdf2image import convert_from_bytes # Naya Import
import json
import re
import sqlite3
import os
import tempfile
import time

# --- Baki code wahi rahega, sirf update ki gayi functions niche hain ---

def analyze_bill(model, images):
    """Multiple images (pages) ko process karne ke liye updated function"""
    prompt = """
    Analyze these images. They contain multiple bills. 
    Extract EACH bill found in the pages.
    Return ONLY a JSON list of objects:
    [
      {"shop_name": "...", "bill_date": "...", "gst_number": "...", "items": [{"name": "...", "qty": "...", "rate": "...", "amount": "..."}], "total": ...}
    ]
    No markdown, no text, just raw JSON.
    """
    # Agar single image hai to list banao
    if not isinstance(images, list): images = [images]
    
    # Model ko images ki list bhejein
    response = model.generate_content([prompt] + images)
    return parse_json_from_response(response.text)

def render_upload_module(model):
    st.markdown('<div class="deep-csc-header">...</div>', unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader("Upload files", type=["jpg", "png", "pdf"], accept_multiple_files=True)

    if not uploaded_files:
        return

    for idx, file in enumerate(uploaded_files):
        st.markdown("---")
        st.subheader(f"📄 Processing: {file.name}")
        
        is_pdf = file.name.lower().endswith(".pdf")
        
        if st.button(f"⚡ Analyze {file.name}", key=f"btn_{idx}"):
            with st.spinner("Processing pages..."):
                try:
                    # PDF to Images conversion
                    if is_pdf:
                        images = convert_from_bytes(file.read())
                    else:
                        images = [Image.open(file)]
                    
                    # AI Analysis
                    results = analyze_bill(model, images)
                    
                    # Results Rendering
                    if isinstance(results, list):
                        for i, bill_data in enumerate(results):
                            st.write(f"### Bill Entry {i+1}")
                            render_bill_result(bill_data, file.name)
                    else:
                        render_bill_result(results, file.name)
                        
                except Exception as e:
                    st.error(f"Error: {e}")
