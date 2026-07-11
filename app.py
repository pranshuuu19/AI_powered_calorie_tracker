"""
app.py

AI Calorie & Nutrition Tracker — Streamlit frontend.

Log meals in natural language (tagged by meal type), have an LLM parse them
into structured nutrition data, persist to SQLite, and view per-meal and
daily totals plus longer-term trends.
"""

import os
from datetime import date, timedelta

import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

import db
import llm_parser
from llm_parser import ParseError

load_dotenv()

st.set_page_config(page_title="AI Calorie & Nutrition Tracker", page_icon="🍽️", layout="wide")

db.init_db()

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    st.error(
        "GROQ_API_KEY not found. Copy `.env.example` to `.env`, add your key, "
        "and restart the app."
    )
    st.stop()
llm_parser.configure(api_key)

st.title("🍽️ AI Calorie & Nutrition Tracker")

with st.sidebar:
    st.header("Daily Goal")
    current_goal = db.get_latest_goal()
    new_goal = st.number_input(
        "Daily calorie goal",
        min_value=0,
        value=int(current_goal) if current_goal else 2000,
        step=50,
    )
    if st.button("Save Goal"):
        db.set_daily_goal(new_goal)
        st.success(f"Goal set to {new_goal} kcal/day")
        st.rerun()

st.subheader("Log a meal")
meal_type = st.selectbox("Which meal is this?", db.MEAL_TYPES)
user_input = st.text_area(
    "Describe what you ate",
    placeholder="e.g. '2 rotis, a bowl of dal, and a banana'",
)

if st.button("Log with AI", type="primary"):
    if not user_input.strip():
        st.warning("Please describe what you ate first.")
    else:
        with st.spinner("Parsing with AI..."):
            try:
                items = llm_parser.parse_food_description(user_input)
                db.insert_food_items(user_input, items, meal_type)
                st.success(f"Logged {len(items)} item(s) under {meal_type}!")
                for item in items:
                    st.write(
                        f"- **{item['food_item']}**: {item['calories']} kcal, "
                        f"{item['protein_g']}g protein, {item['carbs_g']}g carbs, "
                        f"{item['fat_g']}g fat"
                    )
                st.rerun()
            except ParseError as e:
                st.error(f"Couldn't parse that into structured nutrition data: {e}")
            except Exception as e:
                st.error(f"Unexpected error calling the AI: {e}")

st.divider()
st.subheader("Today's Summary")

today = date.today()
today_str = today.isoformat()
meal_totals = db.get_meal_totals(today_str)
day_total = db.get_day_total(today_str)

if meal_totals.empty:
    st.info("No meals logged today yet.")
else:
    meal_cols = st.columns(len(db.MEAL_TYPES))
    for col, meal in zip(meal_cols, db.MEAL_TYPES):
        row = meal_totals[meal_totals["meal_type"] == meal]
        with col:
            if row.empty:
                st.markdown(f"**{meal}**")
                st.caption("Not logged yet")
            else:
                r = row.iloc[0]
                st.markdown(f"**{meal}**")
                st.metric("Calories", f"{r['calories']:.0f} kcal")
                st.caption(f"P {r['protein_g']:.0f}g · C {r['carbs_g']:.0f}g · F {r['fat_g']:.0f}g")

    st.markdown("---")
    goal = db.get_latest_goal()
    goal_text = f" / {goal:.0f} kcal goal" if goal else ""
    st.markdown(
        f"### Day Total: {day_total['calories']:.0f} kcal{goal_text}"
    )
    st.caption(
        f"Protein: {day_total['protein_g']:.0f}g · "
        f"Carbs: {day_total['carbs_g']:.0f}g · "
        f"Fat: {day_total['fat_g']:.0f}g"
    )
    if goal:
        remaining = goal - day_total["calories"]
        if remaining >= 0:
            st.caption(f"{remaining:.0f} kcal remaining today")
        else:
            st.caption(f"{abs(remaining):.0f} kcal over today's goal")

st.divider()
st.subheader("Trends")

range_option = st.radio("Show data for:", ["Last 7 days", "Last 30 days", "All time"], horizontal=True)
if range_option == "Last 7 days":
    start = today - timedelta(days=7)
    logs_df = db.get_logs(start.isoformat(), today_str)
elif range_option == "Last 30 days":
    start = today - timedelta(days=30)
    logs_df = db.get_logs(start.isoformat(), today_str)
else:
    logs_df = db.get_logs()

if logs_df.empty:
    st.info("No meals logged yet. Log your first meal above!")
else:
    daily = (
        logs_df.groupby("log_date")
        .agg(
            calories=("calories", "sum"),
            protein_g=("protein_g", "sum"),
            carbs_g=("carbs_g", "sum"),
            fat_g=("fat_g", "sum"),
        )
        .reset_index()
        .sort_values("log_date")
    )

    goal = db.get_latest_goal()

    fig = px.bar(daily, x="log_date", y="calories", title="Daily Calories")
    if goal:
        fig.add_hline(y=goal, line_dash="dash", line_color="red", annotation_text="Goal")
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(daily, x="log_date", y=["protein_g", "carbs_g", "fat_g"], title="Daily Macros (g)")
    st.plotly_chart(fig2, use_container_width=True)

    # Calories by meal type per day — shows how intake is distributed across
    # breakfast/lunch/snacks/dinner over time, not just the daily total.
    by_meal = (
        logs_df.groupby(["log_date", "meal_type"])
        .agg(calories=("calories", "sum"))
        .reset_index()
    )
    fig3 = px.bar(
        by_meal, x="log_date", y="calories", color="meal_type",
        title="Calories by Meal Type",
        category_orders={"meal_type": db.MEAL_TYPES},
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Logged meals")
    st.dataframe(
        logs_df[["logged_at", "meal_type", "food_item", "calories", "protein_g", "carbs_g", "fat_g", "raw_input"]],
        use_container_width=True,
        hide_index=True,
    )