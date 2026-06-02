import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re

st.set_page_config(page_title="AI Bill Checker", layout="wide")
st.title("🧾 AI Bill Checker")

# Simple File Uploader - Nothing else
uploaded_file = st.file_uploader("Upload Bill Image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    st.image(uploaded_file, use_container_width=True)
    if st.button("Analyze"):
        st.write("Analyzing...")
        # (यहीं पर अपना जेमिनी वाला लॉजिक डालें)
