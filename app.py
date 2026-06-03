import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import subprocess
import os
import platform

# -----------------------------
# ENVIRONMENT DETECTION
# -----------------------------
IS_LOCAL = (
    platform.system() == "Windows"
    and os.path.exists(r"C:\Program Files\NAPS2\NAPS2.Console.exe")
)

# Page Config
st.set_page_config(page_title="Deep CSC - AI Bill Processor", layout="wide")

# API Config
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.0-flash")
except Exception:
    st.error("API Key missing!")
    st.stop()

# -----------------------------
# FUNCTIONS
# -----------------------------
def analyze_bill(image):
    prompt = """
    Extract bill data and return ONLY valid JSON.
    Format:
    {"vendor_name": "", "date": "", "items": [{"name": "", "qty": "", "rate": "", "amount": ""}], "total": ""}
    Rules: Return JSON only, no markdown, no explanation, no ```json, use empty string for null.
    """
    try:
        response = model.generate_content([prompt, image])
        if not response: return None
        raw = getattr(response, "text", "")
        if not raw: return None

        raw = raw.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(raw[start:end + 1])
            else: return None

        if not isinstance(data, dict): return None
        
        # Cleanup
        data["vendor_name"] = str(data.get("vendor_name") or "")
        data["date"] = str(data.get("date") or "")
        data["items"] = data.get("items") or []
        data["total"] = str(data.get("total") or "")
        return data
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

def show_results(data):
    if not isinstance(data, dict):
        st.error("Invalid bill structure")
        return

    st.subheader("📋 Bill Details")
    st.write(f"🏪 Vendor: {str(data.get('vendor_name') or 'Unknown')}")
    st.write(f"🗓️ Invoice Date: {str(data.get('date') or 'Unknown')}")

    items = data.get("items") or []
    if isinstance(items, list) and items:
        clean_rows = []
        for item in items:
            if isinstance(item, dict):
                clean_rows.append({
                    "Name": str(item.get("name") or ""),
                    "Qty": str(item.get("qty") or ""),
                    "Rate": str(item.get("rate") or ""),
                    "Amount": str(item.get("amount") or "")
                })
        if clean_rows:
            st.dataframe(pd.DataFrame(clean_rows), use_container_width=True)
    
    st.metric("💰 Total Amount", f"₹ {str(data.get('total') or '0')}")
    with st.expander("Raw JSON"):
        st.json(data)

# -----------------------------
# UI LOGIC
# -----------------------------
st.title("🧾 Deep CSC - AI Bill Processor")

if IS_LOCAL:
    tab1, tab2 = st.tabs(["📤 Upload & Process", "📠 Scanner"])
else:
    tab1 = st.container()

with tab1:
    uploaded_file = st.file_uploader("Upload Bill Image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, use_column_width=True)
        if st.button("🔍 Analyze Bill"):
            with st.spinner("Analyzing..."):
                data = analyze_bill(image)
                show_results(data)

if IS_LOCAL:
    with tab2:
        if st.button("🚀 Trigger Flatbed Scan"):
            output_file = os.path.abspath("scan.jpg")
            cmd = [r"C:\Program Files\NAPS2\NAPS2.Console.exe", "--driver", "wia", "--device", "Brother DCP-T820DW", "--source", "glass", "--dpi", "300", "-o", output_file, "-f"]
            try:
                subprocess.run(cmd, check=True)
                if os.path.exists(output_file):
                    img = Image.open(output_file)
                    st.image(img, use_column_width=True)
                    data = analyze_bill(img)
                    show_results(data)
            except Exception as e:
                st.error(f"Scanner error: {e}")
