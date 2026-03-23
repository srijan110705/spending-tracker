import streamlit as st
import pandas as pd
from datetime import datetime, date
import pytz
import plotly.express as px
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Spending Dashboard", page_icon="🪙", layout="wide")

def get_today_ist():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).date()

# --- GOOGLE SHEETS SETUP ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Azvpdn9vFelZbti3o8lwkVJqxK4xI2ifa3U-y8s5nTI/edit?usp=drivesdk"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Spendings", ttl=0)
        if df.empty:
            return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])
        df["Note"] = df["Note"].fillna("").astype(str)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])

def save_data(df):
    conn.update(spreadsheet=SHEET_URL, worksheet="Spendings", data=df)

def load_settings():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Settings", ttl=0)
        if not df.empty:
            settings_dict = dict(zip(df['Key'].astype(str), df['Value'].astype(str)))
            settings_dict["limit"] = float(settings_dict.get("limit", 1000.0))
            settings_dict["start_date"] = settings_dict.get("start_date", str(get_today_ist()))
            return settings_dict
    except: pass
    return {"limit": 1000.0, "start_date": str(get_today_ist())}

def save_settings(settings_dict):
    set_df = pd.DataFrame(list(settings_dict.items()), columns=['Key', 'Value'])
    conn.update(spreadsheet=SHEET_URL, worksheet="Settings", data=set_df)

# --- INIT SESSION STATE ---
if "df" not in st.session_state:
    st.session_state.df = load_data()
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

df = st.session_state.df
settings = st.session_state.settings

st.title("💸 Monthly Spending Dashboard")

# --- SIDEBAR: SETTINGS ---
formatted_date = get_today_ist().strftime("%A, %B %d, %Y")
st.sidebar.markdown(f"### 📅 Today: {formatted_date}")

st.sidebar.header("⚙️ Cycle Settings")
base_limit = st.sidebar.number_input("Monthly Limit (₹)", min_value=0.0, value=float(settings.get("limit", 1000.0)), step=100.0)
start_date_input = st.sidebar.date_input("Anchor Start Date", value=date.fromisoformat(settings.get("start_date", str(get_today_ist()))))

if st.sidebar.button("Update Settings"):
    new_settings = {"limit": base_limit, "start_date": str(start_date_input)}
    save_settings(new_settings)
    st.session_state.settings = new_settings
    st.sidebar.success("Settings Updated!")
    st.rerun()

st.sidebar.divider()

# --- INPUT SECTION ---
st.header("Log a Transaction")

def save_transaction():
    amt = st.session_state.amount_input
    if amt > 0:
        raw_category = st.session_state.category_input.strip()
        final_category = raw_category.title() if raw_category else "Miscellaneous"

        new_entry = pd.DataFrame([{
            "Date": str(st.session_state.date_input), 
            "Category": final_category, 
            "Amount": amt,
            "Note": st.session_state.note_input  
        }])
        st.session_state.df = pd.concat([st.session_state.df, new_entry], ignore_index=True)
        save_data
