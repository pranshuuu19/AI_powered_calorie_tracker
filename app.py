import os
from datetime import date, timedelta, datetime

import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

import db
import llm_parser
from llm_parser import ParseError

load_dotenv()

st.set_page_config(page_title="AI Calorie & Nutrition Tracker", page_icon="🍽️", layout="wide")

db.init_db()

def get_api_key():
    """
    Checks os.environ first (local dev via .env), then falls back to
    st.secrets (Streamlit Community Cloud's secrets manager, configured in
    the app's dashboard under Settings -> Secrets — not read from .env,
    since .env is gitignored and never reaches the deployed app).
    """
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return None


api_key = get_api_key()
if not api_key:
    st.error(
        "GROQ_API_KEY not found.\n\n"
        "- Running locally? Copy `.env.example` to `.env` and add your key.\n"
        "- Running on Streamlit Community Cloud? Add it under your app's "
        "**Settings -> Secrets** in the dashboard (not via .env, which never "
        "reaches the deployed app)."
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

    st.divider()
    st.header("💧 Hydration")
    water_today = db.get_water_today()
    st.metric("Glasses today", water_today)
    wc1, wc2 = st.columns(2)
    with wc1:
        if st.button("+1 glass", use_container_width=True):
            db.log_water(1)
            st.rerun()
    with wc2:
        if st.button("+1 bottle (3)", use_container_width=True):
            db.log_water(3)
            st.rerun()

    st.divider()
    streak = db.get_logging_streak()
    if streak > 0:
        st.metric("🔥 Logging streak", f"{streak} day{'s' if streak != 1 else ''}")
    else:
        st.caption("Log a meal today to start a streak!")

st.subheader("Log a meal")

# Quick-add for frequently logged meals — re-inserts the same parsed items
# without another AI call, useful for repetitive hostel/mess meals.
frequent = db.get_frequent_meals(limit=5)
if not frequent.empty:
    with st.expander("⚡ Quick add a frequent meal"):
        quick_meal_type = st.selectbox("Meal", db.MEAL_TYPES, key="quick_meal_type")
        for _, row in frequent.iterrows():
            qcol1, qcol2 = st.columns([4, 1])
            with qcol1:
                st.write(f"{row['raw_input']}  \n:gray[logged {row['times_logged']}x]")
            with qcol2:
                if st.button("Add", key=f"quickadd_{row['raw_input']}"):
                    items = db.get_items_for_raw_input(row["raw_input"])
                    deleted = db.replace_meal_items(row["raw_input"], items, quick_meal_type)
                    if deleted > 0:
                        st.success(f"Updated {quick_meal_type}: replaced {deleted} previous item(s) with '{row['raw_input']}'")
                    else:
                        st.success(f"Re-logged '{row['raw_input']}' under {quick_meal_type}")
                    st.rerun()

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
                deleted = db.replace_meal_items(user_input, items, meal_type)
                if deleted > 0:
                    st.success(f"Updated {meal_type}: replaced {deleted} previous item(s) with {len(items)} new item(s).")
                else:
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
    st.markdown(f"### Day Total: {day_total['calories']:.0f} kcal{goal_text}")
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

    # Gentle, non-judgmental nudges — informational only, never alarmist.
    nudges = []
    if day_total["calories"] > 0:
        protein_calories = day_total["protein_g"] * 4
        protein_pct = protein_calories / day_total["calories"] * 100
        if protein_pct < 15:
            nudges.append(
                "Protein looks a bit low relative to today's other macros — "
                "dal, eggs, paneer, curd, or chana are cheap, easy ways to round it out."
            )
    current_hour = datetime.now().hour
    if current_hour >= 14 and meal_totals[meal_totals["meal_type"] == "Breakfast"].empty:
        nudges.append("No breakfast logged today — not a problem if that's intentional, just flagging it.")
    for n in nudges:
        st.caption(f"💡 {n}")

    # 7-day rolling average — smooths out single-day noise (exam days, etc.)
    rolling = db.get_rolling_average(days=7)
    if rolling["days_logged"] > 1:
        st.caption(
            f"📊 7-day average ({rolling['days_logged']} day(s) logged): "
            f"{rolling['calories']:.0f} kcal/day · "
            f"P {rolling['protein_g']:.0f}g · C {rolling['carbs_g']:.0f}g · F {rolling['fat_g']:.0f}g"
        )

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