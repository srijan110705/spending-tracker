import streamlit as st
import pandas as pd
from datetime import datetime, date
import pytz
import os
import json
import plotly.express as px

def get_today_ist():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).date()

# --- FILE SETUP ---
DATA_FILE = "my_spendings.csv"
SETTINGS_FILE = "settings.json"

def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        if "Note" not in df.columns:
            df["Note"] = ""
        df["Note"] = df["Note"].fillna("") 
        return df
    else:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    else:
        return {"limit": 1000.0, "start_date": str(get_today_ist())}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

st.set_page_config(page_title="Spending Dashboard", layout="wide")
st.title("💸 Monthly Spending Dashboard")

if "df" not in st.session_state:
    st.session_state.df = load_data()
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

df = st.session_state.df
settings = st.session_state.settings

# --- SIDEBAR: SETTINGS & BACKUP ---
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
        save_data(st.session_state.df)
        
        st.session_state.amount_input = 0.0 
        st.session_state.note_input = "" 
        st.session_state.category_input = "" 
        st.toast("Transaction Saved Successfully!", icon="✅")

with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        st.date_input("Date", get_today_ist(), key="date_input") 
        st.text_input("Category", placeholder="e.g. Food, Taxi", key="category_input")
    with col2:
        st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="amount_input")
        st.text_input("Short Note (Optional)", key="note_input")
    st.button("Save Entry", type="primary", on_click=save_transaction)

# --- CYCLE GENERATOR ENGINE ---
df_calc = st.session_state.df.copy()
anchor_ts = pd.Timestamp(settings["start_date"])
today_ts = pd.Timestamp(get_today_ist())

if not df_calc.empty:
    max_df_ts = pd.to_datetime(df_calc["Date"]).max()
    target_end_ts = max(today_ts, max_df_ts)
else:
    target_end_ts = today_ts

available_cycles = []
current_iter = anchor_ts
for _ in range(24): 
    next_iter = current_iter + pd.DateOffset(months=1)
    end_display = next_iter - pd.Timedelta(days=1)
    available_cycles.append({
        "label": f"{current_iter.strftime('%b %d, %Y')} to {end_display.strftime('%b %d, %Y')}",
        "start": current_iter.date(),
        "end": next_iter.date() 
    })
    if next_iter > target_end_ts: break
    current_iter = next_iter
available_cycles.reverse()

# --- DASHBOARD SECTION ---
st.header("📊 Cycle Analysis")
selected_label = st.selectbox("📅 Select Cycle to View", [c["label"] for c in available_cycles])
selected_cycle = next(c for c in available_cycles if c["label"] == selected_label)

if not df_calc.empty:
    df_calc["DateObj"] = pd.to_datetime(df_calc["Date"]).dt.date
    active_cycle_df = df_calc[(df_calc["DateObj"] >= selected_cycle["start"]) & (df_calc["DateObj"] < selected_cycle["end"])]
else:
    active_cycle_df = pd.DataFrame()

# 1. Totals
total_spent = 0.0
parent_spent = 0.0
if not active_cycle_df.empty:
    is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
    total_spent = active_cycle_df[~is_parent]["Amount"].sum()
    parent_spent = active_cycle_df[is_parent]["Amount"].sum()

monthly_limit = settings["limit"] 
remaining_budget = monthly_limit - total_spent

# 2. Averages Math
cycle_start = selected_cycle["start"]
cycle_end = selected_cycle["end"]
today = get_today_ist()

# Calculate days passed
if today >= cycle_end:
    days_passed = (cycle_end - cycle_start).days
    days_left = 0
elif today < cycle_start:
    days_passed = 0
    days_left = (cycle_end - cycle_start).days
else:
    days_passed = (today - cycle_start).days + 1
    days_left = (cycle_end - today).days

# Metrics
daily_avg = total_spent / days_passed if days_passed > 0 else 0.0
target_daily = remaining_budget / days_left if days_left > 0 else 0.0

# 3. Display Metrics
st.markdown(f"**Cycle Status:** Day {days_passed} of {(cycle_end-cycle_start).days}")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Personal Spent", f"₹{total_spent:,.2f}")
m2.metric("Parent Total", f"₹{parent_spent:,.2f}")
m3.metric("Limit", f"₹{monthly_limit:,.2f}")
m4.metric("Remaining", f"₹{remaining_budget:,.2f}", delta=f"{remaining_budget:,.2f}", delta_color="normal" if remaining_budget >= 0 else "inverse")

st.divider()

# 4. Display Averages
st.subheader("💡 Spending Pacing")
avg_col1, avg_col2 = st.columns(2)

with avg_col1:
    st.metric("Actual Daily Average", f"₹{daily_avg:,.2f} / day")
    st.caption(f"Based on {days_passed} days in this cycle.")

with avg_col2:
    if days_left > 0:
        if remaining_budget > 0:
            st.metric("Target Daily Average", f"₹{target_daily:,.2f} / day")
            st.caption(f"Maintain this to stay under your ₹{monthly_limit} limit for the next {days_left} days.")
        else:
            st.metric("Target Daily Average", "₹0.00", delta="Over Limit", delta_color="inverse")
            st.caption("You have already exhausted your budget for this cycle.")
    else:
        st.metric("Target Daily Average", "N/A")
        st.caption("Cycle has ended.")

st.divider()

# --- GRAPHS SECTION ---
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Total by Category")
    if not active_cycle_df.empty:
        # Filter out Parent
        is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
        spendings_df = active_cycle_df[~is_parent].copy()
        
        if not spendings_df.empty:
            spendings_df["CleanCategory"] = spendings_df["Category"].str.strip().str.title()
            category_totals = spendings_df.groupby("CleanCategory")["Amount"].sum().reset_index()
            
            # --- CUSTOM LEGEND LOGIC ---
            # Create a new column for the legend that includes the category name AND the amount
            category_totals["LegendLabel"] = category_totals.apply(
                lambda row: f"{row['CleanCategory']}: ₹{row['Amount']:,.2f}", axis=1
            )
            
            # Build the pie chart using the new LegendLabel for the 'names' parameter
            fig = px.pie(
                category_totals, 
                values="Amount", 
                names="LegendLabel", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            
            # Clean up the chart appearance
            fig.update_traces(textinfo='percent', textposition='inside')
            fig.update_layout(
                legend_title_text='Category : Amount',
                legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.0)
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No personal spending in this cycle.")
    else:
        st.info("No data available for this cycle.")

with col_chart2:
    st.subheader("Daily Spending Trend")
    if not active_cycle_df.empty:
        is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
        daily_df = active_cycle_df[~is_parent].copy()
        if not daily_df.empty:
            daily_df["Date"] = pd.to_datetime(daily_df["Date"])
            daily_trend = daily_df.groupby("Date")["Amount"].sum()
            st.line_chart(daily_trend)
        else:
            st.info("No daily data to trend.")
    else:
        st.info("No data available.")

with col_chart2:
    st.subheader("Daily Trend")
    if not active_cycle_df.empty:
        is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
        daily_df = active_cycle_df[~is_parent].copy()
        daily_df["Date"] = pd.to_datetime(daily_df["Date"])
        daily_trend = daily_df.groupby("Date")["Amount"].sum()
        st.line_chart(daily_trend)

st.divider()
st.subheader("Master Ledger")
display_df = st.session_state.df.copy()
display_df["SortDate"] = pd.to_datetime(display_df["Date"])
display_df = display_df.sort_values(by="SortDate", ascending=False).drop(columns=["SortDate"])
edited_df = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, hide_index=True)

if not edited_df.equals(display_df):
    st.session_state.df = edited_df.sort_values(by="Date", ascending=True).reset_index(drop=True)
    save_data(st.session_state.df)
    st.rerun()
