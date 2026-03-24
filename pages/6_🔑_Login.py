"""
pages/6_🔑_Login.py
===================
Authentication page.
"""

from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from src.auth import login, signup, is_authenticated

st.set_page_config(page_title="Log In | MetricSleuth", page_icon="🔑", layout="centered")

# CSS
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Space Grotesk', sans-serif; }
.stApp { background: #060912; color: #c9d1e3; }
.stButton > button {
    background: linear-gradient(135deg, #00e5ff, #7b68ee);
    color: #060912; border: none; border-radius: 8px;
    font-weight: 700; font-size: 0.85rem; letter-spacing: 1.5px;
    text-transform: uppercase; padding: .7rem 2rem;
    transition: opacity .15s; width: 100%;
}
.stButton > button:hover { opacity: .82; }
.stTextInput > div > input {
    background: #0d1327; border: 1px solid #1e2d52;
    color: #c9d1e3; border-radius: 8px; padding: 0.6rem 1rem;
}
.stTextInput > div > input:focus { border-color: #00e5ff; box-shadow: 0 0 0 2px rgba(0,229,255,.15); }
.auth-card {
    background: #0b0f1e; border: 1px solid #1a2040;
    border-radius: 16px; padding: 2.5rem;
    box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
</style>""", unsafe_allow_html=True)

if is_authenticated():
    st.success("You are already logged in!")
    if st.button("Go to Dashboard"):
        st.switch_page("pages/2_📊_Dashboard.py")
    st.stop()

st.markdown('<div class="auth-card">', unsafe_allow_html=True)

mode = st.radio(
    "mode", ["Log In", "Sign Up"],
    horizontal=True, label_visibility="collapsed",
)
st.markdown("<br>", unsafe_allow_html=True)

if mode == "Log In":
    email    = st.text_input("Email", placeholder="you@company.com", key="li_email")
    password = st.text_input("Password", type="password", placeholder="••••••••", key="li_pass")
    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("Log In", key="btn_login"):
        if not email or not password:
            st.error("Please enter your email and password.")
        else:
            with st.spinner("Authenticating…"):
                ok, msg = login(email, password)
            if ok:
                st.success(msg)
                st.switch_page("pages/2_📊_Dashboard.py")
            else:
                st.error(msg)
else:  # Sign Up
    full_name = st.text_input("Full name", placeholder="Jane Smith", key="su_name")
    email     = st.text_input("Email", placeholder="you@company.com", key="su_email")
    password  = st.text_input("Password (min 6 chars)", type="password", placeholder="••••••••", key="su_pass")
    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("Create Free Account", key="btn_signup"):
        if not email or not password:
            st.error("Email and password are required.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            with st.spinner("Creating account…"):
                ok, msg = signup(email, password, full_name)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

st.markdown('</div>', unsafe_allow_html=True)
