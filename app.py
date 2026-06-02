import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
import sqlite3
import re
from datetime import datetime
import time

# Page Setup
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Dashboard UI (Ye aapka purana layout hai)
st.title("🧾 AI Multi-Bill OCR Processor")

uploaded_files = st.file_uploader("Upload Bill Images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    for file in uploaded_files:
        st.image(file)
        # Yahan apna baaki processing logic rakhein
        
# Yadi aapko Scanner/Printer wahi chahiye, toh use sirf 'Local' machine par chalaayein:
# st.warning("Hardware control only works if you run this app on your own computer.")
