import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import urllib.parse
import tempfile
import json
import re
import sqlite3
from datetime import datetime
import time

# -------------------------
# PAGE CONFIG & BRANDING
# -------------------------
st.set_page_config(
    page_title="Deep CSC - AI Bill Processor Premium",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Deep CSC Ultimate Colorful UI/UX Premium Stylesheet
st.markdown("""
    <style>
        /* Modern Fluid Theme Reset */
        .main { background-color: #f8fafc; }
        h1, h2, h3, h4 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: #0f172a !important; font-weight: 800 !important; }
        
        /* Deep CSC Premium Dynamic Branding Header */
        .deep-csc-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            padding: 30px;
            border-radius: 24px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            margin-bottom: 35px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 20px;
        }
        .branding-text h1 { 
            background: linear-gradient(to right, #38bdf8, #c084fc, #f43f5e); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent;
            margin: 0; 
            font-size: 34px !important; 
            letter-spacing: -0.5px; 
        }
        .csc-meta-badge {
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 10px 18px;
            border-radius: 14px;
            color: #e2e8f0 !important;
            font-size: 13px !important;
            line-height: 1.6;
        }
        .branding-badge {
            background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%);
            color: white !important;
            padding: 8px 18px;
            border-radius: 50px;
            font-size: 13px !important;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            box-shadow: 0 4px 14px rgba(236, 72, 153, 0.4);
        }
        
        /* Colorful Glowing Dashboard Metrics Cards */
        div[data-testid="stMetric"] {
            background: #ffffff !important;
            padding: 24px !important;
            border-radius: 20px !important;
            box-shadow: 0 12px 20px -3px rgba(15, 23, 42, 0.04), 0 4px 6px -4px rgba(15, 23, 42, 0.04) !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-5px);
            box-shadow: 0 25px 30px -5px rgba(15, 23, 42, 0.08) !important;
        }
        
        div[data-testid="stMetricValue"] {
            font-size: 36px !important;
            font-weight: 800 !important;
            letter-spacing: -1px;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 12px !important;
            text-transform: uppercase !important;
            letter-spacing: 1px !important;
            font-weight: 700 !important;
            color: #64748b !important;
            margin-bottom: 8px;
        }

        /* Sidebar Styling */
        .stSidebar { background-color: #0f172a !important; }
        
        /* Action Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            padding: 12px 24px !important;
            border-radius: 12px !important;
            border: none !important;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.2) !important;
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(79, 70, 229, 0.35) !important;
        }
    </style>
""", unsafe_allow_html=True)

# -------------------------
# DATABASE SETUP
# -------------------------
def init_db():
    conn = sqlite3.connect("bills.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT,
            bill_date TEXT,
            gst_number TEXT,
            total REAL,
            calculated_total REAL,
            status TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def insert_bill(shop, date, gst, total, calc_total, status
