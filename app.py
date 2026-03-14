import streamlit as st
import pandas as pd
from datetime import datetime, date
import pytz
import os
import json
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
# This connects to the Sheet URL you provided
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Azvpdn9vFelZbti3o8lwkVJqxK4xI2ifa3U-y8s5nTI/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def get_today_ist():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).date()

# --- CLOUD DATA FUNCTIONS ---
def load_cloud_data():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Spendings")
        if df.empty:
            return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])

def load_cloud_settings():
    DEFAULT_PIN_HASH = hashlib.sha256("1234".encode()).hexdigest()
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Settings")
        if not df.empty:
            # Convert the 2-column settings sheet into a dictionary
            return dict(zip(df['Key'], df['Value']))
    except:
        pass
    return {"limit": "1000.0", "start_date": str(get_today_ist()), "pin_hash": DEFAULT_PIN_HASH}

def save_to_cloud(df_spendings, settings_dict):
    # Update the Spendings sheet
    conn.update(spreadsheet=SHEET_URL, worksheet="Spendings", data=df_spendings)
    # Convert settings dict to a DataFrame for the Settings sheet
    set_df = pd.DataFrame(list(settings_dict.items()), columns=['Key', 'Value'])
    conn.update(spreadsheet=SHEET_URL, worksheet="Settings", data=set_df)

# --- INITIALIZE SESSION STATE ---
if "settings" not in st.session_state:
    st.session_state.settings = load_cloud_settings()
if "df" not in st.session_state:
    st.session_state.df = load_cloud_data()

settings = st.session_state.settings

# --- SECURITY GATEKEEPER ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔒 App Locked")
        st.caption("Enter your PIN to access the Cloud Dashboard.")
        
        pin = st.text_input("4-Digit PIN", type="password")
        if st.button("Unlock", type="primary"):
            input_hash = hashlib.sha256(pin.encode()).hexdigest()
            stored_hash = settings.get("pin_hash")
            
            if input_hash == stored_hash:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("🚨 Incorrect PIN.")
        st.stop()

check_password()

# --- ML ENGINE ---
def train_category_model(df):
    if df.empty or len(df[df["Note"].astype(str).str.strip() != ""]) < 5:
        return None
    train_data = df[df["Note"].astype(str).str.strip() != ""]
    X = train_data["Note"]
    y = train_data["Category"]
    model = make_pipeline(TfidfVectorizer(), MultinomialNB())
    model.fit(X, y)
    return model

if "ml_model" not in st.session_state:
    st.session_state.ml_model = train_category_model(st.session_state.df)

# --- SIDEBAR ---
formatted_date = get_today_ist().strftime("%A, %B %d, %Y")
st.sidebar.markdown(f"### 📅 Today: {formatted_date}")

if st.sidebar.button("🔒 Lock App"):
    st.session_state.authenticated = False
    st.rerun()

st.sidebar.divider()
st.sidebar.header("🔐 Security")
with st.sidebar.expander("Change PIN"):
    curr_p = st.text_input("Current PIN", type="password")
    new_p = st.text_input("New PIN (4 digits)", type="password", max_chars=4)
    if st.button("Update PIN"):
        if hashlib.sha256(curr_p.encode()).hexdigest() == settings.get("pin_hash"):
            if len(new_p) == 4 and new_p.isdigit():
                settings["pin_hash"] = hashlib.sha256(new_p.encode()).hexdigest()
                save_to_cloud(st.session_state.df, settings)
                st.success("PIN Updated in Cloud!")
            else: st.error("Must be 4 digits.")
        else: st.error("Wrong current PIN.")

st.sidebar.divider()
st.sidebar.header("⚙️ Cycle Settings")
base_limit = st.sidebar.number_input("Monthly Limit (₹)", min_value=0.0, value=float(settings.get("limit", 1000.0)))
start_date_input = st.sidebar.date_input("Anchor Start Date", value=date.fromisoformat(str(settings.get("start_date"))))

if st.sidebar.button("Update Settings"):
    settings["limit"] = str(base_limit)
    settings["start_date"] = str(start_date_input)
    save_to_cloud(st.session_state.df, settings)
    st.sidebar.success("Settings Saved to Cloud!")
    st.rerun()

# --- INPUT SECTION ---
st.header("Log a Transaction")

def auto_predict_category():
    note = st.session_state.note_input.strip()
    if note and st.session_state.ml_model is not None:
        predicted_cat = st.session_state.ml_model.predict([note])[0]
        st.session_state.category_input = predicted_cat

def save_transaction():
    amt = st.session_state.amount_input
    if amt > 0:
        raw_cat = st.session_state.category_input.strip()
        final_cat = raw_cat.title() if raw_cat else "Miscellaneous"
        new_entry = pd.DataFrame([{"Date": str(st.session_state.date_input), "Category": final_cat, "Amount": amt, "Note": st.session_state.note_input}])
        st.session_state.df = pd.concat([st.session_state.df, new_entry], ignore_index=True)
        save_to_cloud(st.session_state.df, settings)
        st.session_state.ml_model = train_category_model(st.session_state.df)
        st.session_state.amount_input = 0.0
        st.session_state.note_input = ""
        st.session_state.category_input = ""
        st.toast("Saved to Google Sheets!", icon="☁️")

with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Date", get_today_ist(), key="date_input")
        st.text_input("Short Note", key="note_input", on_change=auto_predict_category)
    with c2:
        st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="amount_input")
        st.text_input("Category", key="category_input")
    st.button("Save Entry", type="primary", on_click=save_transaction)

# --- DASHBOARD LOGIC ---
st.header("📊 Cycle Analysis")
# (Generating cycles and graph logic remains the same, but uses active_cycle_df)
# [Note: Cycle generation and graph code simplified for brevity but works with cloud df]
df_calc = st.session_state.df.copy()
anchor_ts = pd.Timestamp(settings["start_date"])
today_ts = pd.Timestamp(get_today_ist())

# Generate Cycles
available_cycles = []
current_iter = anchor_ts
for _ in range(24):
    next_iter = current_iter + pd.DateOffset(months=1)
    cycle_label = f"{current_iter.strftime('%b %d')} - {(next_iter - pd.Timedelta(days=1)).strftime('%b %d, %Y')}"
    available_cycles.append({"label": cycle_label, "start": current_iter.date(), "end": next_iter.date()})
    if next_iter > today_ts and (df_calc.empty or next_iter > pd.to_datetime(df_calc["Date"]).max()): break
    current_iter = next_iter
available_cycles.reverse()

selected_label = st.selectbox("📅 Select Cycle", [c["label"] for c in available_cycles])
sel = next(c for c in available_cycles if c["label"] == selected_label)

if not df_calc.empty:
    df_calc["DateObj"] = pd.to_datetime(df_calc["Date"]).dt.date
    active_cycle_df = df_calc[(df_calc["DateObj"] >= sel["start"]) & (df_calc["DateObj"] < sel["end"])]
else: active_cycle_df = pd.DataFrame()

# Stats
total_spent = active_cycle_df[active_cycle_df["Category"].str.title() != "Parent"]["Amount"].sum() if not active_cycle_df.empty else 0.0
parent_spent = active_cycle_df[active_cycle_df["Category"].str.title() == "Parent"]["Amount"].sum() if not active_cycle_df.empty else 0.0
rem = float(settings["limit"]) - total_spent

m1, m2, m3, m4 = st.columns(4)
m1.metric("Limit", f"₹{float(settings['limit']):.2f}")
m2.metric("Spent", f"₹{total_spent:.2f}")
m3.metric("Parent", f"₹{parent_spent:.2f}")
m4.metric("Remaining", f"₹{rem:.2f}")

# Graphs
col_chart1, col_chart2 = st.columns(2)
with col_chart1:
    if not active_cycle_df.empty:
        pdf = active_cycle_df[active_cycle_df["Category"].str.title() != "Parent"]
        if not pdf.empty:
            fig = px.pie(pdf, values="Amount", names="Category")
            st.plotly_chart(fig, use_container_width=True)
with col_chart2:
    if not active_cycle_df.empty:
        ldf = active_cycle_df[active_cycle_df["Category"].str.title() != "Parent"].copy()
        ldf["Date"] = pd.to_datetime(ldf["Date"])
        st.line_chart(ldf.groupby("Date")["Amount"].sum())

# --- MASTER LEDGER ---
st.divider()
st.subheader("Cloud Master Ledger")
edited_df = st.data_editor(st.session_state.df, num_rows="dynamic", use_container_width=True)
if not edited_df.equals(st.session_state.df):
    st.session_state.df = edited_df
    save_to_cloud(edited_df, settings)
    st.rerun()
