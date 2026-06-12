import base64
import json
import os
import re
import sqlite3
import urllib.parse
import warnings
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

warnings.filterwarnings("ignore")

try:
    import fitz
except Exception:
    fitz = None

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

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
    from google.cloud import vision
except Exception:
    vision = None

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except Exception:
    service_account = None
    build = None
    MediaFileUpload = None

APP_TITLE = "Deep CSC - AI Bill Processor Premium"
DB_PATH = "bills.db"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROVIDERS = ["Gemini", "Google Vision OCR", "Perplexity", "OpenAI"]


@dataclass
class OCRResult:
    shop_name: str
    bill_date: str
    gst_number: str
    items: list
    total: float
    raw_text: str = ""


def secret_or_default(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return default


def setup_page():
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide", initial_sidebar_state="expanded")


def init_state():
    defaults = {
        "logged_in": False,
        "selected_provider": "Gemini",
        "theme_mode": "light",
        "processed_files": set(),
        "gemini_available": True,
        "last_gemini_error_time": None,
        "gemini_cooldown_seconds": 900,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def init_db():
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_name TEXT NOT NULL,
                bill_date TEXT NOT NULL,
                gst_number TEXT,
                total REAL NOT NULL,
                calculated_total REAL NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                UNIQUE(shop_name, bill_date, total)
            )
            """
        )


def login_screen():
    st.markdown(
        """
        <style>
        .login-wrap {
            max-width: 460px;
            margin: 7vh auto;
            padding: 28px;
            border-radius: 24px;
            background: rgba(255,255,255,0.85);
            box-shadow: 0 20px 60px rgba(15, 23, 42, 0.14);
            border: 1px solid rgba(148,163,184,0.18);
            backdrop-filter: blur(10px);
        }
        .login-title {
            font-size: 32px;
            font-weight: 800;
            margin: 0;
            background: linear-gradient(to right, #0f172a, #4338ca);
            -webkit-background-clip: 
