import streamlit as st
import pandas as pd
from datetime import date
import os
import json
import plotly.express as px

# --- FILE SETUP ---
DATA_FILE = "my_spendings.csv"
SETTINGS_FILE = "settings.json"
# The hardcoded SPENDING_CATEGORIES list has been completely removed.

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
        return {"limit": 1000.0, "start_date": str(date.today())}

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
formatted_date = date.today().strftime("%A, %B %d, %Y")
st.sidebar.markdown(f"### 📅 Today: {formatted_date}")

st.sidebar.header("⚙️ Cycle Settings")
st.sidebar.caption("This start date acts as the anchor for all your monthly cycles.")
base_limit = st.sidebar.number_input("Monthly Limit (₹)", min_value=0.0, value=float(settings.get("limit", 1000.0)), step=100.0)
start_date_input = st.sidebar.date_input("Anchor Start Date", value=date.fromisoformat(settings.get("start_date", str(date.today()))))

if st.sidebar.button("Update Settings"):
    new_settings = {
        "limit": base_limit, 
        "start_date": str(start_date_input)
    }
    save_settings(new_settings)
    st.session_state.settings = new_settings
    st.sidebar.success("Settings Updated!")
    st.rerun()

st.sidebar.divider()

st.sidebar.header("💾 Data Backup")
st.sidebar.caption("Download a safe copy of your history.")
csv_data = df.to_csv(index=False).encode('utf-8')
st.sidebar.download_button(
    label="Download CSV Backup",
    data=csv_data,
    file_name=f"spending_backup_{date.today()}.csv",
    mime="text/csv"
)

# --- INPUT SECTION ---
st.header("Log a Transaction")

def save_transaction():
    amt = st.session_state.amount_input
    if amt > 0:
        # Dynamic Category Logic: Clean up the text or default to Miscellaneous
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
        
        # Reset the inputs
        st.session_state.amount_input = 0.0 
        st.session_state.note_input = "" 
        st.session_state.category_input = "" # Auto-clear the category box too
        st.toast("Transaction Saved Successfully!", icon="✅")

with st.container(border=True):
    col1, col2 = st.columns(2)
    
    with col1:
        st.date_input("Date", date.today(), key="date_input") 
        # Replaced the dropdown with a dynamic text input
        st.text_input("Category", placeholder="e.g. Food, Taxi (Defaults to Miscellaneous)", key="category_input")
        
    with col2:
        st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="amount_input")
        st.text_input("Short Note (Optional)", placeholder="e.g., Movie tickets...", key="note_input")
    
    st.button("Save Entry", type="primary", on_click=save_transaction)

# --- CYCLE GENERATOR ENGINE ---
df_calc = st.session_state.df.copy()
anchor_ts = pd.Timestamp(settings["start_date"])
today_ts = pd.Timestamp(date.today())

if not df_calc.empty:
    max_df_ts = pd.to_datetime(df_calc["Date"]).max()
    target_end_ts = max(today_ts, max_df_ts)
else:
    target_end_ts = today_ts

available_cycles = []
current_iter = anchor_ts

for _ in range(120): 
    next_iter = current_iter + pd.DateOffset(months=1)
    end_display = next_iter - pd.Timedelta(days=1)
    
    cycle_label = f"{current_iter.strftime('%b %d, %Y')} to {end_display.strftime('%b %d, %Y')}"
    available_cycles.append({
        "label": cycle_label,
        "start": current_iter.date(),
        "end": next_iter.date() 
    })
    
    if next_iter > target_end_ts:
        break
    current_iter = next_iter

available_cycles.reverse() 

# --- PACING & DASHBOARD SECTION ---
st.header("📊 Cycle Analysis")

selected_label = st.selectbox("📅 Select Cycle to View", [c["label"] for c in available_cycles])
selected_cycle = next(c for c in available_cycles if c["label"] == selected_label)

if not df_calc.empty:
    df_calc["DateObj"] = pd.to_datetime(df_calc["Date"]).dt.date
    active_cycle_df = df_calc[(df_calc["DateObj"] >= selected_cycle["start"]) & (df_calc["DateObj"] < selected_cycle["end"])]
else:
    active_cycle_df = pd.DataFrame()

# 1. Totals & Limits
total_spent = 0.0
parent_spent = 0.0

if not active_cycle_df.empty:
    # Ensure backward compatibility by checking for "Parent" regardless of how it was typed
    is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
    
    total_spent = active_cycle_df[~is_parent]["Amount"].sum()
    parent_spent = active_cycle_df[is_parent]["Amount"].sum()

monthly_limit = settings["limit"] 
remaining_budget = monthly_limit - total_spent

# 2. Smart Math for Historical vs Current Cycles
cycle_start_date = selected_cycle["start"]
cycle_end_date = selected_cycle["end"]
today = date.today()

is_past = today >= cycle_end_date
is_current = (today >= cycle_start_date) and (today < cycle_end_date)

cycle_length = (cycle_end_date - cycle_start_date).days 

if is_past:
    days_completed = cycle_length 
elif is_current:
    days_completed = (today - cycle_start_date).days + 1
else:
    days_completed = 1

days_remaining = cycle_length - days_completed
if days_remaining < 0:
    days_remaining = 0

current_average = total_spent / days_completed
target_average = remaining_budget / days_remaining if days_remaining > 0 else 0

# 3. Display Core Metrics
st.markdown(f"**Cycle:** {selected_label} *(Day {days_completed} of {cycle_length})*")

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("Monthly Limit", f"₹{monthly_limit:.2f}")
metric_col2.metric("Personal Spent", f"₹{total_spent:.2f}")
metric_col3.metric("Parent Spent", f"₹{parent_spent:.2f}")
metric_col4.metric("Remaining Budget", f"₹{remaining_budget:.2f}")

st.divider()
avg_col1, avg_col2 = st.columns(2)
avg_col1.metric("Average Spending", f"₹{current_average:.2f} / day")
avg_col1.caption(f"*(Math: ₹{total_spent:.2f} ÷ {days_completed} completed days)*")

if is_past:
    avg_col2.metric("Target Average to Maintain", "Cycle Ended")
elif remaining_budget >= 0 and days_remaining > 0:
    avg_col2.metric("Target Average to Maintain", f"₹{target_average:.2f} / day")
    avg_col2.caption(f"*(Math: ₹{remaining_budget:.2f} ÷ {days_remaining} days left)*")
elif days_remaining <= 0:
    avg_col2.metric("Target Average to Maintain", "Cycle Ended")
else:
    avg_col2.metric("Target Average to Maintain", "₹0.00 / day", delta="Over Limit", delta_color="inverse")

# 4. Smart Alerts
if not is_past:
    if remaining_budget < 0:
        st.error(f"🚨 ALERT: You have crossed your limit by ₹{abs(remaining_budget):.2f}! Time to spend less.")
    elif remaining_budget < (monthly_limit * 0.1):
        st.warning(f"⚠️ Careful! You are down to your last ₹{remaining_budget:.2f}.")
    else:
        st.success("✅ You are staying within your personal budget!")
else:
    if remaining_budget < 0:
        st.error(f"Cycle finished over budget by ₹{abs(remaining_budget):.2f}.")
    else:
        st.success(f"Cycle finished under budget with ₹{remaining_budget:.2f} remaining.")

st.divider()

# 5. Graphs
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Total by Category")
    
    if not active_cycle_df.empty:
        # Filter out Parent cleanly
        is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
        spendings_df = active_cycle_df[~is_parent].copy()
        
        # Standardize the text for grouping just in case there are formatting variations
        spendings_df["CleanCategory"] = spendings_df["Category"].str.strip().str.title()
        category_totals = spendings_df.groupby("CleanCategory")["Amount"].sum() if not spendings_df.empty else pd.Series(dtype=float)
    else:
        category_totals = pd.Series(dtype=float)
        
    pie_data = category_totals.reset_index()
    pie_data.columns = ["Category", "Amount"]
    pie_data = pie_data[pie_data["Amount"] > 0]
    
    if not pie_data.empty:
        fig = px.pie(pie_data, values="Amount", names="Category")
        fig.update_traces(textposition='inside', textinfo='value', texttemplate='₹%{value:,.2f}')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No personal spending to chart yet.")
    
with col_chart2:
    st.subheader("Daily Spending Trend")
    
    if is_past:
        graph_end_date = cycle_end_date - pd.Timedelta(days=1)
    else:
        graph_end_date = today
        if not active_cycle_df.empty:
            is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
            spendings_df = active_cycle_df[~is_parent].copy()
            if not spendings_df.empty:
                spendings_df["DateDT"] = pd.to_datetime(spendings_df["Date"])
                max_entry_date = spendings_df["DateDT"].max().date()
                if max_entry_date > graph_end_date:
                    graph_end_date = max_entry_date
        cycle_inclusive_end = cycle_end_date - pd.Timedelta(days=1)
        if graph_end_date > cycle_inclusive_end:
            graph_end_date = cycle_inclusive_end
            
    if not active_cycle_df.empty:
        is_parent = active_cycle_df["Category"].str.strip().str.title() == "Parent"
        spendings_df = active_cycle_df[~is_parent].copy()
        if not spendings_df.empty:
            spendings_df["DateDT"] = pd.to_datetime(spendings_df["Date"])
            daily_totals = spendings_df.groupby("DateDT")["Amount"].sum()
        else:
            daily_totals = pd.Series(dtype=float)
    else:
        daily_totals = pd.Series(dtype=float)
        
    full_calendar = pd.date_range(start=cycle_start_date, end=graph_end_date)
    daily_totals = daily_totals.reindex(full_calendar, fill_value=0.0)
    daily_totals.index = daily_totals.index.strftime('%b %d')
    st.line_chart(daily_totals)

# --- Master Ledger (Edit History) ---
st.divider()
st.subheader("Master Ledger (All Transactions)")
st.caption("Fix a typo? Click any cell below to edit it, or select a row to delete it. Changes save automatically.")

display_df = st.session_state.df.copy()
display_df["SortDate"] = pd.to_datetime(display_df["Date"])
display_df = display_df.sort_values(by="SortDate", ascending=False).drop(columns=["SortDate"])

edited_df = st.data_editor(
    display_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Category": st.column_config.TextColumn("Category"), # Unlocked category editing
        "Amount": st.column_config.NumberColumn("Amount", format="₹%.2f", min_value=0.0),
        "Note": st.column_config.TextColumn("Note")
    }
)

if not edited_df.equals(display_df):
    st.session_state.df = edited_df.sort_values(by="Date", ascending=True).reset_index(drop=True)
    save_data(st.session_state.df)
    st.rerun()
