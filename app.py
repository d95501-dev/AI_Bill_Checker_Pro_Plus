import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import sqlite3
import hashlib
import json
import re
import os
import time
import platform
from datetime import datetime
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- Config & Setup ---
st.set_page_config(page_title="Deep CSC AI Premium", layout="wide")

# Corrected Syntax for IS_LOCAL
IS_LOCAL = (platform.system() == "Windows" and os.path.exists(r"C:\Program Files\NAPS2\NAPS2.Console.exe"))

genai.configure(api_key=st.secrets.get("GEMINI_API_KEY", ""))
model = genai.GenerativeModel("gemini-1.5-flash")

def init_db():
    conn = sqlite3.connect("bills.db")
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS bills 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_name TEXT, total REAL, status TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Utility Functions ---
def validate_gst(gst):
    if not gst or gst == "": return False, "N/A"
    gst = str(gst).upper().strip()
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    return bool(re.match(pattern, gst)), gst

def analyze_bill(image):
    prompt = "Extract shop_name, bill_date, gst_number, total, and items (list of {name, qty, rate, amount}) as JSON."
    try:
        response = model.generate_content([prompt, image])
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except:
        return None

# --- UI & Core Logic ---
st.title("🧾 Deep CSC AI Bill Processor")

uploaded_file = st.file_uploader("Upload Bill Image", type=["jpg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, width=300)
    
    if st.button("🚀 Analyze Bill"):
        with st.spinner("AI Processing..."):
            data = analyze_bill(image)
            if data:
                st.success("Analysis Complete!")
                st.json(data)
                
                # Auto Save
                conn = sqlite3.connect("bills.db")
                cur = conn.cursor()
                cur.execute("INSERT INTO bills (shop_name, total, status, timestamp) VALUES (?,?,?,?)",
                            (data.get("shop_name", "Unknown"), data.get("total", 0), "Processed", datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                conn.close()
                
                # Download Options
                df = pd.DataFrame(data.get("items", []))
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📊 Download CSV", csv, "bill_data.csv", "text/csv")
            else:
                st.error("AI could not parse the image. Try a clearer scan.")

# --- Simple Dashboard ---
if st.checkbox("Show Database"):
    conn = sqlite3.connect("bills.db")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    st.dataframe(df)
    conn.close()
