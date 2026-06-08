import base64
import json
import os
import re
import sqlite3
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

# --- (Keep all your existing imports and helper functions as they are until render_theme_toggle) ---

# ... [KEEP ALL YOUR EXISTING IMPORTS AND FUNCTIONS UNCHANGED] ...
# ... [Start replacing from render_theme_toggle onwards] ...

def render_theme_toggle(key_suffix=""):
    """Updated function to support dynamic keys and prevent duplicate errors"""
    if "theme_mode" not in st.session_state:
        st.session_state["theme_mode"] = "light"
    
    # Unique key generate karne ke liye suffix ka use kiya
    mode = st.radio(
        "Theme", 
        ["light", "dark"], 
        horizontal=True, 
        index=0 if st.session_state.get("theme_mode", "light") == "light" else 1, 
        key=f"theme_radio_{key_suffix}"
    )
    
    if mode != st.session_state.get("theme_mode", "light"):
        st.session_state["theme_mode"] = mode
        st.rerun()

def render_upload_module():
    st.markdown(
        """
        <div class="deep-csc-header">
            <div class="branding-text">
                <h1>🧾 AI Multi-Bill OCR Processor</h1>
                <p style="color: #94a3b8; margin: 5px 0 0 0;">Automated structural data parsing pipeline powered by multiple providers.</p>
            </div>
            <div class="csc-meta-badge">📍 <b>Deep CSC</b><br>👤 Owner: Deepak | ID: 256423250015</div>
            <div class="branding-badge">Deep CSC AI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["📷 Scan / Upload", "🕘 History", "⚙️ Settings"])

    with tabs[0]:
        # ... [Keep your existing logic for scan/upload] ...
        # (Rest of your original scan/upload code goes here)
        pass

    with tabs[1]:
        st.subheader("History")
        # ... [Keep your existing history logic] ...
        pass

    with tabs[2]:
        st.subheader("Settings")
        # Yahan unique suffix pass kiya
        render_theme_toggle(key_suffix="settings_tab")
        st.caption("Provider order is sequential and fail-fast for speed.")

def main():
    setup_page()
    init_db()
    init_auth()
    init_runtime_state()
    apply_theme_css()
    apply_css()

    if not st.session_state.logged_in:
        do_login()

    with st.sidebar:
        st.markdown(
            """
            <div style="padding:12px;border:1px solid rgba(255,255,255,0.14);border-radius:14px;">
                <div style="font-size:22px;font-weight:800;">Deep CSC</div>
                <div style="font-size:16px;font-weight:700;margin-top:4px;">AI Bill Processor</div>
                <div style="font-size:13px;opacity:0.95;margin-top:8px;">ID: 256423250015</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Yahan sidebar ke liye alag unique suffix pass kiya
        render_theme_toggle(key_suffix="sidebar")
        
        if st.button("Logout", use_container_width=True):
            terminate_session()

    render_upload_module()

if __name__ == "__main__":
    main()
