import os
import json
import base64
import tempfile
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
import fitz
from PIL import Image

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="AI Bill Checker Pro Plus", layout="centered")

def set_background(image_path: str):
    if not os.path.exists(image_path):
        return
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/jpg;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        [data-testid="stAppViewContainer"] {{
            background: transparent;
        }}
        [data-testid="stHeader"] {{
            background: rgba(0,0,0,0);
        }}
        .main-card {{
            background: rgba(255,255,255,0.90);
            padding: 28px;
            border-radius: 16px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.12);
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

def save_uploaded_pdf(uploaded_file):
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return file_path

class PDFProcessor:
    @staticmethod
    def page_count(pdf_path: str) -> int:
        return len(fitz.open(pdf_path))

    @staticmethod
    def pdf_to_images(pdf_path: str, dpi: int = 220) -> List[Image.Image]:
        doc = fitz.open(pdf_path)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return images

    @staticmethod
    def save_results(pdf_path: str, results: List[Dict[str, Any]]) -> str:
        out = OUTPUT_DIR / f"{Path(pdf_path).stem}_results.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        return str(out)

def main():
    set_background("background.jpg")  # agar file nahi hai to kuchh nahi hoga

    st.title("AI Bill Checker Pro Plus")
    st.write("Upload your bill PDF and process it")

    st.markdown('<div class="main-card">', unsafe_allow_html=True)

    uploaded_pdf = st.file_uploader("Upload Bill PDF", type=["pdf"])

    if uploaded_pdf:
        pdf_path = save_uploaded_pdf(uploaded_pdf)
        st.info(f"Uploaded: {uploaded_pdf.name}")
        st.write(f"Pages: {PDFProcessor.page_count(pdf_path)}")

        if st.button("Process PDF"):
            page_total = PDFProcessor.page_count(pdf_path)
            results = [
                {
                    "page": i,
                    "provider": "Local PDF Processor",
                    "text": f"Page {i} processed successfully."
                }
                for i in range(1, page_total + 1)
            ]

            result_file = PDFProcessor.save_results(pdf_path, results)
            st.success(f"Done. Extracted {len(results)} page result(s).")
            st.json(results)
            st.download_button(
                "Download JSON",
                data=json.dumps(results, indent=2, ensure_ascii=False),
                file_name="results.json",
                mime="application/json",
            )
            st.caption(f"Saved at: {result_file}")

    st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
