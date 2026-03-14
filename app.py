import streamlit as st
import pandas as pd
from datetime import datetime, date
import pytz
import hashlib
import plotly.express as px
from streamlit_gsheets import GSheetsConnection

# --- MACHINE LEARNING IMPORTS ---
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline

# --- PAGE SETUP ---
st.set_page_config(page_title="Spending Dashboard", page_icon="🪙", layout="wide")

# --- GOOGLE SHEETS CONNECTION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Azvpdn9vFelZbti3o8lwkVJqxK4xI2ifa3U-y8s5nTI/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def get_today_ist():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).date()

# --- DATA LOADERS ---
def load_cloud_data():
    try:
        # ttl=0 ensures we always get the freshest data from your Sheet
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Spendings", ttl=0)
        if df.empty:
            return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])
        df["Note"] = df["Note"].fillna("").astype(str)
        df["Category"] = df["Category"].fillna("Miscellaneous").astype(str)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])

def load_cloud_settings():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Settings", ttl=0)
        if not df.empty:
            return dict(zip(df['Key'].astype(str), df['Value'].astype(str)))
    except:
        pass
    return {"limit": "1000.0", "start_date": str(get_today_ist())}

def save_to_cloud(df_spendings, settings_dict):
    conn.update(spreadsheet=SHEET_URL, worksheet="Spendings", data=df_spendings)
    set_df = pd.DataFrame(list(settings_dict.items()), columns=['Key', 'Value'])
    conn.update(spreadsheet=SHEET_URL, worksheet="Settings", data=set_df)

# Initialize Session State
if "settings" not in st.session_state:
    st.session_state.settings = load_cloud_settings()
if "df" not in st.session_state:
    st.session_state.df = load_cloud_data()

settings = st.session_state.settings

# --- ML ENGINE ---
def train_category_model(df):
    # Filter rows that have both a note and a category
    train_data = df[(df["Note"].str.strip() != "") & (df["Category"].notna())]
    if len(train_data) < 5:
        return None
    model = make_pipeline(TfidfVectorizer(), MultinomialNB())
    model.fit(train_data["Note"], train_data["Category"])
    return model

if "ml_model" not in st.session_state:
    st.session_state.ml_model = train_category_model(st.session_state.df)

# --- APP UI ---
st.title("💸 Monthly Spending Dashboard")

# SIDEBAR
st.sidebar.markdown(f"### 📅 Today: {get_today_ist().strftime('%A, %B %d')}")
st.sidebar.divider()
st.sidebar.header("⚙️ Settings")
base_limit = st.sidebar.number_input("Monthly Limit (₹)", value=float(settings.get("limit", 1000.0)))
if st.sidebar.button("Update Settings"):
    settings["limit"] = str(base_limit)
    save_to_cloud(st.session_state.df, settings)
    st.sidebar.success("Settings Saved!")

# INPUT FORM
st.header("Log a Transaction")

def auto_predict_category():
    note = st.session_state.note_input.strip()
    if note and st.session_state.ml_model is not None:
        try:
            predicted = st.session_state.ml_model.predict([note])[0]
            st.session_state.category_input = predicted
        except:
            pass

def save_transaction():
    if st.session_state.amount_input > 0:
        new_row = {
            "Date": str(st.session_state.date_input),
            "Category": st.session_state.category_input.strip().title() or "Miscellaneous",
            "Amount": st.session_state.amount_input,
            "Note": st.session_state.note_input
        }
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
        save_to_cloud(st.session_state.df, settings)
        st.session_state.ml_model = train_category_model(st.session_state.df)
        st.toast("Transaction Synced to Google Sheets!", icon="☁️")

with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Date", get_today_ist(), key="date_input")
        st.text_input("Short Note", key="note_input", placeholder="e.g. Zomato", on_change=auto_predict_category)
    with c2:
        st.number_input("Amount (₹)", min_value=0.0, key="amount_input")
        st.text_input("Category", key="category_input", placeholder="Predicts from Note...")
    st.button("Save Entry", type="primary", on_click=save_transaction)

# ANALYSIS SECTION
st.divider()
st.header("📊 Spending Analysis")

df_display = st.session_state.df.copy()
if not df_display.empty:
    df_display["Date"] = pd.to_datetime(df_display["Date"])
    
    # Logic: "Parent" category is tracked but excluded from personal budget
    personal_df = df_display[df_display["Category"] != "Parent"]
    parent_df = df_display[df_display["Category"] == "Parent"]
    
    total_personal = personal_df["Amount"].sum()
    total_parent = parent_df["Amount"].sum()
    remaining = float(settings.get("limit", 1000.0)) - total_personal
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Personal Spent", f"₹{total_personal:,.2f}")
    m2.metric("Parent Spent", f"₹{total_parent:,.2f}")
    m3.metric("Budget Left", f"₹{remaining:,.2f}", delta=f"{remaining:,.2f}", delta_color="normal" if remaining >=0 else "inverse")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Personal Breakdown")
        if not personal_df.empty:
            fig = px.pie(personal_df, values="Amount", names="Category", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with col_b:
        st.subheader("Daily Trend")
        if not personal_df.empty:
            trend = personal_df.groupby("Date")["Amount"].sum()
            st.line_chart(trend)

# MASTER LEDGER
st.divider()
st.subheader("📝 Master Ledger (Edit Directly)")
st.caption("Changes here sync automatically to Google Sheets.")
edited_df = st.data_editor(st.session_state.df, num_rows="dynamic", use_container_width=True, hide_index=True)

if not edited_df.equals(st.session_state.df):
    st.session_state.df = edited_df
    save_to_cloud(edited_df, settings)
    st.rerun()
