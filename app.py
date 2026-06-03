import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re
import sqlite3
from datetime import datetime

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills 
                      (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# API Config
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def analyze_bill(image):
    # Prompt में confidence score की मांग की है
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {
        "shop_name": "", "bill_date": "", "total": "",
        "items": [{"name": "", "qty": "", "rate": "", "amount": ""}],
        "confidence_score": 0
    }
    Rules: Return JSON only. No markdown. Use "" for empty fields.
    """
    try:
        response = model.generate_content([prompt, image])
        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# UI Logic
st.title("🧾 Deep CSC - AI Bill Processor")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, use_container_width=True)
    
    if st.button("🔍 Analyze Bill"):
        with st.spinner("Processing..."):
            data = analyze_bill(image)
            
            if data:
                st.subheader("📋 Edit & Confirm Data")
                # Confidence Score Check
                score = data.get("confidence_score", 0)
                st.info(f"AI Confidence: {score}%")
                
                # Editable Table
                items_df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(items_df, use_container_width=True)
                
                total = data.get("total", 0)
                st.metric("💰 Total Amount", f"₹ {total}")
                
                if st.button("💾 Save to Database"):
                    # Database Logic
                    conn = sqlite3.connect("bills.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO bills (shop_name, bill_date, total, status) VALUES (?,?,?,?)", 
                                   (data.get("shop_name"), data.get("bill_date"), total, "Verified"))
                    conn.commit()
                    conn.close()
                    st.success("Data Saved Successfully!")
            else:
                st.error("Failed to parse bill. Please upload a clear image.")import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re
import sqlite3
from datetime import datetime

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills 
                      (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# API Config
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def analyze_bill(image):
    # Prompt में confidence score की मांग की है
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {
        "shop_name": "", "bill_date": "", "total": "",
        "items": [{"name": "", "qty": "", "rate": "", "amount": ""}],
        "confidence_score": 0
    }
    Rules: Return JSON only. No markdown. Use "" for empty fields.
    """
    try:
        response = model.generate_content([prompt, image])
        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# UI Logic
st.title("🧾 Deep CSC - AI Bill Processor")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, use_container_width=True)
    
    if st.button("🔍 Analyze Bill"):
        with st.spinner("Processing..."):
            data = analyze_bill(image)
            
            if data:
                st.subheader("📋 Edit & Confirm Data")
                # Confidence Score Check
                score = data.get("confidence_score", 0)
                st.info(f"AI Confidence: {score}%")
                
                # Editable Table
                items_df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(items_df, use_container_width=True)
                
                total = data.get("total", 0)
                st.metric("💰 Total Amount", f"₹ {total}")
                
                if st.button("💾 Save to Database"):
                    # Database Logic
                    conn = sqlite3.connect("bills.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO bills (shop_name, bill_date, total, status) VALUES (?,?,?,?)", 
                                   (data.get("shop_name"), data.get("bill_date"), total, "Verified"))
                    conn.commit()
                    conn.close()
                    st.success("Data Saved Successfully!")
            else:
                st.error("Failed to parse bill. Please upload a clear image.")import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re
import sqlite3
from datetime import datetime

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills 
                      (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# API Config
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def analyze_bill(image):
    # Prompt में confidence score की मांग की है
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {
        "shop_name": "", "bill_date": "", "total": "",
        "items": [{"name": "", "qty": "", "rate": "", "amount": ""}],
        "confidence_score": 0
    }
    Rules: Return JSON only. No markdown. Use "" for empty fields.
    """
    try:
        response = model.generate_content([prompt, image])
        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# UI Logic
st.title("🧾 Deep CSC - AI Bill Processor")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, use_container_width=True)
    
    if st.button("🔍 Analyze Bill"):
        with st.spinner("Processing..."):
            data = analyze_bill(image)
            
            if data:
                st.subheader("📋 Edit & Confirm Data")
                # Confidence Score Check
                score = data.get("confidence_score", 0)
                st.info(f"AI Confidence: {score}%")
                
                # Editable Table
                items_df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(items_df, use_container_width=True)
                
                total = data.get("total", 0)
                st.metric("💰 Total Amount", f"₹ {total}")
                
                if st.button("💾 Save to Database"):
                    # Database Logic
                    conn = sqlite3.connect("bills.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO bills (shop_name, bill_date, total, status) VALUES (?,?,?,?)", 
                                   (data.get("shop_name"), data.get("bill_date"), total, "Verified"))
                    conn.commit()
                    conn.close()
                    st.success("Data Saved Successfully!")
            else:
                st.error("Failed to parse bill. Please upload a clear image.")import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re
import sqlite3
from datetime import datetime

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills 
                      (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# API Config
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def analyze_bill(image):
    # Prompt में confidence score की मांग की है
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {
        "shop_name": "", "bill_date": "", "total": "",
        "items": [{"name": "", "qty": "", "rate": "", "amount": ""}],
        "confidence_score": 0
    }
    Rules: Return JSON only. No markdown. Use "" for empty fields.
    """
    try:
        response = model.generate_content([prompt, image])
        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# UI Logic
st.title("🧾 Deep CSC - AI Bill Processor")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, use_container_width=True)
    
    if st.button("🔍 Analyze Bill"):
        with st.spinner("Processing..."):
            data = analyze_bill(image)
            
            if data:
                st.subheader("📋 Edit & Confirm Data")
                # Confidence Score Check
                score = data.get("confidence_score", 0)
                st.info(f"AI Confidence: {score}%")
                
                # Editable Table
                items_df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(items_df, use_container_width=True)
                
                total = data.get("total", 0)
                st.metric("💰 Total Amount", f"₹ {total}")
                
                if st.button("💾 Save to Database"):
                    # Database Logic
                    conn = sqlite3.connect("bills.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO bills (shop_name, bill_date, total, status) VALUES (?,?,?,?)", 
                                   (data.get("shop_name"), data.get("bill_date"), total, "Verified"))
                    conn.commit()
                    conn.close()
                    st.success("Data Saved Successfully!")
            else:
                st.error("Failed to parse bill. Please upload a clear image.")import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re
import sqlite3
from datetime import datetime

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills 
                      (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# API Config
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def analyze_bill(image):
    # Prompt में confidence score की मांग की है
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {
        "shop_name": "", "bill_date": "", "total": "",
        "items": [{"name": "", "qty": "", "rate": "", "amount": ""}],
        "confidence_score": 0
    }
    Rules: Return JSON only. No markdown. Use "" for empty fields.
    """
    try:
        response = model.generate_content([prompt, image])
        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# UI Logic
st.title("🧾 Deep CSC - AI Bill Processor")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, use_container_width=True)
    
    if st.button("🔍 Analyze Bill"):
        with st.spinner("Processing..."):
            data = analyze_bill(image)
            
            if data:
                st.subheader("📋 Edit & Confirm Data")
                # Confidence Score Check
                score = data.get("confidence_score", 0)
                st.info(f"AI Confidence: {score}%")
                
                # Editable Table
                items_df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(items_df, use_container_width=True)
                
                total = data.get("total", 0)
                st.metric("💰 Total Amount", f"₹ {total}")
                
                if st.button("💾 Save to Database"):
                    # Database Logic
                    conn = sqlite3.connect("bills.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO bills (shop_name, bill_date, total, status) VALUES (?,?,?,?)", 
                                   (data.get("shop_name"), data.get("bill_date"), total, "Verified"))
                    conn.commit()
                    conn.close()
                    st.success("Data Saved Successfully!")
            else:
                st.error("Failed to parse bill. Please upload a clear image.")import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import re
import sqlite3
from datetime import datetime

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bills 
                      (id INTEGER PRIMARY KEY, shop_name TEXT, bill_date TEXT, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# API Config
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def analyze_bill(image):
    # Prompt में confidence score की मांग की है
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {
        "shop_name": "", "bill_date": "", "total": "",
        "items": [{"name": "", "qty": "", "rate": "", "amount": ""}],
        "confidence_score": 0
    }
    Rules: Return JSON only. No markdown. Use "" for empty fields.
    """
    try:
        response = model.generate_content([prompt, image])
        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# UI Logic
st.title("🧾 Deep CSC - AI Bill Processor")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, use_container_width=True)
    
    if st.button("🔍 Analyze Bill"):
        with st.spinner("Processing..."):
            data = analyze_bill(image)
            
            if data:
                st.subheader("📋 Edit & Confirm Data")
                # Confidence Score Check
                score = data.get("confidence_score", 0)
                st.info(f"AI Confidence: {score}%")
                
                # Editable Table
                items_df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(items_df, use_container_width=True)
                
                total = data.get("total", 0)
                st.metric("💰 Total Amount", f"₹ {total}")
                
                if st.button("💾 Save to Database"):
                    # Database Logic
                    conn = sqlite3.connect("bills.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO bills (shop_name, bill_date, total, status) VALUES (?,?,?,?)", 
                                   (data.get("shop_name"), data.get("bill_date"), total, "Verified"))
                    conn.commit()
                    conn.close()
                    st.success("Data Saved Successfully!")
            else:
                st.error("Failed to parse bill. Please upload a clear image.")
