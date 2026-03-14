import streamlit as st
import pandas as pd
from datetime import datetime, date
import pytz
import os
import json
import hashlib
import plotly.express as px
from streamlit_gsheets import GSheetsConnection

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline

st.set_page_config(page_title="Spending Dashboard", page_icon="🪙", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1Azvpdn9vFelZbti3o8lwkVJqxK4xI2ifa3U-y8s5nTI/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def get_today_ist():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).date()

def load_cloud_data():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Spendings", ttl=0)
        df["Note"] = df["Note"].fillna("").astype(str)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])

def load_cloud_settings():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Settings", ttl=0)
        if not df.empty:
            return dict(zip(df['Key'].astype(str), df['Value'].astype(str)))
    except: pass
    return {"limit": "1000.0", "start_date": str(get_today_ist())}

def save_to_cloud(df_spendings, settings_dict):
    conn.update(spreadsheet=SHEET_URL, worksheet="Spendings", data=df_spendings)
    set_df = pd.DataFrame(list(settings_dict.items()), columns=['Key', 'Value'])
    conn.update(spreadsheet=SHEET_URL, worksheet="Settings", data=set_df)

if "settings" not in st.session_state:
    st.session_state.settings = load_cloud_settings()
if "df" not in st.session_state:
    st.session_state.df = load_cloud_data()

settings = st.session_state.settings

# --- ML ENGINE ---
def train_category_model(df):
    df["Note"] = df["Note"].fillna("").astype(str)
    train_data = df[(df["Note"].str.strip() != "") & (df["Category"].notna())]
    if len(train_data) < 5: return None
    model = make_pipeline(TfidfVectorizer(), MultinomialNB())
    model.fit(train_data["Note"], train_data["Category"])
    return model

if "ml_model" not in st.session_state:
    st.session_state.ml_model = train_category_model(st.session_state.df)

# --- AUTO-PREDICT LOGIC ---
def auto_predict():
    note = st.session_state.note_input.strip()
    if note and st.session_state.ml_model is not None:
        try:
            pred = st.session_state.ml_model.predict([note])[0]
            st.session_state.category_input = pred
        except: pass

st.title("💸 Monthly Spending Dashboard")

# --- SIDEBAR ---
st.sidebar.markdown(f"### 📅 Today: {get_today_ist().strftime('%A, %B %d')}")

st.sidebar.header("⚙️ Cycle Settings")
base_limit = st.sidebar.number_input("Monthly Limit (₹)", value=float(settings.get("limit", 1000.0)))
anchor_date = st.sidebar.date_input("Anchor Start Date", value=date.fromisoformat(str(settings.get("start_date", get_today_ist()))))

if st.sidebar.button("Update Settings"):
    settings["limit"] = str(base_limit)
    settings["start_date"] = str(anchor_date)
    save_to_cloud(st.session_state.df, settings)
    st.sidebar.success("Saved!")
    st.rerun()

# --- LOGGING ---
st.header("Log a Transaction")
def save_transaction():
    if st.session_state.amount_input > 0:
        new_entry = pd.DataFrame([{"Date": str(st.session_state.date_input), "Category": st.session_state.category_input.title(), "Amount": st.session_state.amount_input, "Note": st.session_state.note_input}])
        st.session_state.df = pd.concat([st.session_state.df, new_entry], ignore_index=True)
        save_to_cloud(st.session_state.df, settings)
        st.session_state.ml_model = train_category_model(st.session_state.df)
        st.toast("Saved to Cloud!")

with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Date", get_today_ist(), key="date_input")
        st.text_input("Short Note", key="note_input", on_change=auto_predict)
    with c2:
        st.number_input("Amount (₹)", min_value=0.0, key="amount_input")
        st.text_input("Category", key="category_input")
    st.button("Save Entry", type="primary", on_click=save_transaction)

# --- DASHBOARD & AVERAGES ---
st.header("📊 Pacing Analysis")
df_calc = st.session_state.df.copy()
if not df_calc.empty:
    df_calc["Date"] = pd.to_datetime(df_calc["Date"])
    
    # Core Totals
    personal_df = df_calc[df_calc["Category"] != "Parent"]
    total = personal_df["Amount"].sum()
    parent = df_calc[df_calc["Category"] == "Parent"]["Amount"].sum()
    limit = float(settings.get("limit", 1000.0))
    rem = limit - total
    
    # Math for Pacing
    today = get_today_ist()
    cycle_start = date.fromisoformat(str(settings.get("start_date", today)))
    days_passed = (today - cycle_start).days + 1
    if days_passed <= 0: days_passed = 1
    
    daily_avg = total / days_passed
    
    # Assume 30-day cycle for target pacing
    days_left = 30 - days_passed
    target_pacing = rem / days_left if days_left > 0 else 0

    # Top Row Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Personal Spent", f"₹{total:,.2f}")
    m2.metric("Parent Spent", f"₹{parent:,.2f}")
    m3.metric("Remaining", f"₹{rem:,.2f}", delta=f"{rem:,.2f}", delta_color="normal" if rem >= 0 else "inverse")
    
    # Average Metrics
    st.divider()
    a1, a2 = st.columns(2)
    a1.metric("Actual Average", f"₹{daily_avg:,.2f} / day")
    if days_left > 0:
        a2.metric("Target Average to Maintain", f"₹{max(0, target_pacing):,.2f} / day")
    else:
        a2.metric("Target Average", "Cycle End")

    st.subheader("Category Breakdown")
    fig = px.pie(personal_df, values="Amount", names="Category", hole=0.3)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Master Ledger")
edited_df = st.data_editor(st.session_state.df, num_rows="dynamic", use_container_width=True, hide_index=True)
if not edited_df.equals(st.session_state.df):
    st.session_state.df = edited_df
    save_to_cloud(edited_df, settings)
    st.rerun()
