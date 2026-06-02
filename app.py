import streamlit as st
import subprocess
import os

st.set_page_config(page_title="Deep CSC", layout="wide")

st.title("🧾 Deep CSC - AI Bill Processor")

def hardware_module():
    st.markdown("### 🔌 Advanced Hardware Controller")
    with st.expander("🖨️ Scanner & Printer Console", expanded=True):
        if st.button("🚀 Open Brother Scanner"):
            # सही पाथ जो आपके पीसी के स्क्रीनशॉट में दिखा
            scanner_path = r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe"
            if os.path.exists(scanner_path):
                subprocess.Popen(scanner_path)
                st.success("Brother Scanner opened!")
            else:
                st.error(f"Scanner software not found at: {scanner_path}")

        if st.button("🖨️ Open Print Dialog"):
            st.components.v1.html("<script>window.print();</script>", height=0)

# सिर्फ लोकल मशीन पर ही हार्डवेयर मॉड्यूल दिखाएं
if os.name == 'nt': # यह केवल Windows पर चलेगा
    hardware_module()

st.markdown("---")
uploaded_file = st.file_uploader("Upload Bill", type=["jpg", "png"])
if uploaded_file:
    st.image(uploaded_file)
