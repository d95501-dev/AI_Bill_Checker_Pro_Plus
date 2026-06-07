import base64
import json
import re
import sqlite3
import tempfile
import subprocess
import os
import sys
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

try:
    from pdf2image import convert_from_bytes
except Exception:
    convert_from_bytes = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import requests
except Exception:
    requests = None

try:
    from google.cloud import vision
except Exception:
    vision = None

try:
    from google.cloud import documentai
except Exception:
    documentai = None

try:
    import boto3
except Exception:
    boto3 = None

try:
    import win32print
    WINDOWS_PRINTER_AVAILABLE = True
except Exception:
    WINDOWS_PRINTER_AVAILABLE = False

import warnings
warnings.filterwarnings("ignore")

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"

NAPS2_GUI_PATH = r"C:\Program Files\NAPS2\NAPS2.exe"
NAPS2_CONSOLE_PATH = r"C:\Program Files\NAPS2\NAPS2.Console.exe"
BROTHER_APP_PATH = r"C:\Program Files (x86)\Brother\iPrint&Scan\Brother iPrint&Scan.exe"
SCAN_OUTPUT_DIR = r"C:\Scans"


def secret_or_default(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return default


DEFAULT_USERNAME = secret_or_default("APP_USERNAME", "admin")
DEFAULT_PASSWORD = secret_or_default("APP_PASSWORD", "password123")


def setup_page():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def apply_css():
    st.markdown(
        """
        <style>
        .main { background-color: #f8fafc; }
        h1, h2, h3, h4 { font-family: system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
        .deep-csc-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            padding: 30px; border-radius: 24px; margin-bottom: 35px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px;
        }
        .branding-text h1 {
            background: linear-gradient(to right, #38bdf8, #c084fc, #f43f5e);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin: 0; font-size: 34px !important; letter-spacing: -0.5px;
        }
        .csc-meta-badge {
            background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 10px 18px; border-radius: 14px; color: #e2e8f0 !important; font-size: 13px !important; line-height: 1.6;
        }
        .branding-badge {
            background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%);
            color: white !important;
            padding: 10px 14px;
            border-radius: 12px;
            font-weight: 700;
            display: inline-block;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    setup_page()
    apply_css()
    st.title("Deep CSC - AI Bill Processor Premium")
    st.success("App loaded successfully.")

if __name__ == "__main__":
    main()
