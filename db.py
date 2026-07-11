"""
db.py

SQLite persistence layer for the AI Calorie & Nutrition Tracker.
No Streamlit or LLM dependencies here on purpose — keeps this module
independently testable.
"""

import os
import sqlite3
from datetime import datetime, date, timedelta

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tracker.db")

MEAL_TYPES = ["Breakfast", "Lunch", "Snacks", "Dinner"]


def init_db(db_path: str = DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at TEXT NOT NULL,
            log_date TEXT NOT NULL,
            meal_type TEXT NOT NULL DEFAULT 'Unspecified',
            raw_input TEXT NOT NULL,
            food_item TEXT NOT NULL,
            calories REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL
        )
    """)
    # Migration path: if an older tracker.db exists from before meal_type was
    # added, add the column instead of crashing on missing-column errors.
    cur.execute("PRAGMA table_info(logs)")
    existing_cols = [row[1] for row in cur.fetchall()]
    if "meal_type" not in existing_cols:
        cur.execute("ALTER TABLE logs ADD COLUMN meal_type TEXT NOT NULL DEFAULT 'Unspecified'")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            daily_calorie_goal REAL NOT NULL,
            set_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS water_logs (
            log_date TEXT PRIMARY KEY,
            glasses INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def insert_food_items(raw_input: str, items: list, meal_type: str, db_path: str = DB_PATH):
    """items: list of dicts with keys food_item, calories, protein_g, carbs_g, fat_g"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now = datetime.now().isoformat()
    today = date.today().isoformat()
    for item in items:
        cur.execute("""
            INSERT INTO logs (logged_at, log_date, meal_type, raw_input, food_item, calories, protein_g, carbs_g, fat_g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, today, meal_type, raw_input, item["food_item"], item["calories"],
              item["protein_g"], item["carbs_g"], item["fat_g"]))
    conn.commit()
    conn.close()


def get_logs(start_date: str = None, end_date: str = None, db_path: str = DB_PATH) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    query = "SELECT * FROM logs"
    params = []
    if start_date and end_date:
        query += " WHERE log_date BETWEEN ? AND ?"
        params = [start_date, end_date]
    query += " ORDER BY logged_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_meal_totals(target_date: str, db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Returns per-meal totals (calories, protein_g, carbs_g, fat_g) for a given
    date, one row per meal type that has at least one logged item, ordered
    Breakfast -> Lunch -> Snacks -> Dinner.
    """
    df = get_logs(target_date, target_date, db_path)
    if df.empty:
        return pd.DataFrame(columns=["meal_type", "calories", "protein_g", "carbs_g", "fat_g"])

    totals = (
        df.groupby("meal_type")
        .agg(
            calories=("calories", "sum"),
            protein_g=("protein_g", "sum"),
            carbs_g=("carbs_g", "sum"),
            fat_g=("fat_g", "sum"),
        )
        .reset_index()
    )
    totals["meal_type"] = pd.Categorical(totals["meal_type"], categories=MEAL_TYPES, ordered=True)
    return totals.sort_values("meal_type").reset_index(drop=True)


def get_day_total(target_date: str, db_path: str = DB_PATH) -> dict:
    """Returns the full-day total across all meals for a given date."""
    df = get_logs(target_date, target_date, db_path)
    if df.empty:
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    return {
        "calories": float(df["calories"].sum()),
        "protein_g": float(df["protein_g"].sum()),
        "carbs_g": float(df["carbs_g"].sum()),
        "fat_g": float(df["fat_g"].sum()),
    }


def get_rolling_average(days: int = 7, db_path: str = DB_PATH) -> dict:
    """
    Returns the average daily calories/macros over the trailing `days` days
    (including today), based on days that actually have at least one log —
    days with zero entries aren't counted as zeros, so a single day off
    doesn't unfairly drag the average down.
    """
    end = date.today()
    start = end - timedelta(days=days - 1)
    df = get_logs(start.isoformat(), end.isoformat(), db_path)
    if df.empty:
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "days_logged": 0}

    daily = df.groupby("log_date").agg(
        calories=("calories", "sum"),
        protein_g=("protein_g", "sum"),
        carbs_g=("carbs_g", "sum"),
        fat_g=("fat_g", "sum"),
    )
    return {
        "calories": float(daily["calories"].mean()),
        "protein_g": float(daily["protein_g"].mean()),
        "carbs_g": float(daily["carbs_g"].mean()),
        "fat_g": float(daily["fat_g"].mean()),
        "days_logged": int(len(daily)),
    }


def get_logging_streak(db_path: str = DB_PATH) -> int:
    """
    Returns the number of consecutive days (ending today or yesterday) with
    at least one logged meal. Ending at yesterday is allowed so the streak
    doesn't reset to 0 first thing in the morning before today's first log.
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT DISTINCT log_date FROM logs", conn)
    conn.close()
    if df.empty:
        return 0

    logged_dates = set(pd.to_datetime(df["log_date"]).dt.date)
    cursor = date.today()
    if cursor not in logged_dates:
        cursor -= timedelta(days=1)
        if cursor not in logged_dates:
            return 0

    streak = 0
    while cursor in logged_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_frequent_meals(limit: int = 5, db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Returns the most frequently logged distinct meal descriptions (by raw
    text input), across all meal types, ordered by how many times logged.
    Powers the "log again" quick-add feature so repeat meals (common with
    hostel/mess food) don't need a fresh AI parse every time.
    """
    conn = sqlite3.connect(db_path)
    query = """
        SELECT raw_input,
               COUNT(DISTINCT logged_at) AS times_logged,
               MAX(logged_at) AS last_logged
        FROM logs
        GROUP BY raw_input
        ORDER BY times_logged DESC, last_logged DESC
        LIMIT ?
    """
    df = pd.read_sql_query(query, conn, params=[limit])
    conn.close()
    return df


def get_items_for_raw_input(raw_input: str, db_path: str = DB_PATH) -> list:
    """
    Returns the most recently logged set of food items for a given raw
    description, so they can be re-inserted without another AI call.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT MAX(logged_at) FROM logs WHERE raw_input = ?", (raw_input,))
    last_logged_at = cur.fetchone()[0]
    if not last_logged_at:
        conn.close()
        return []
    cur.execute("""
        SELECT food_item, calories, protein_g, carbs_g, fat_g
        FROM logs WHERE raw_input = ? AND logged_at = ?
    """, (raw_input, last_logged_at))
    rows = cur.fetchall()
    conn.close()
    return [
        {"food_item": r[0], "calories": r[1], "protein_g": r[2], "carbs_g": r[3], "fat_g": r[4]}
        for r in rows
    ]


def log_water(glasses: int = 1, db_path: str = DB_PATH):
    today = date.today().isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO water_logs (log_date, glasses) VALUES (?, ?)
        ON CONFLICT(log_date) DO UPDATE SET glasses = glasses + excluded.glasses
    """, (today, glasses))
    conn.commit()
    conn.close()


def get_water_today(db_path: str = DB_PATH) -> int:
    today = date.today().isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT glasses FROM water_logs WHERE log_date = ?", (today,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def set_daily_goal(calories: float, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO goals (daily_calorie_goal, set_at) VALUES (?, ?)",
                (calories, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_latest_goal(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT daily_calorie_goal FROM goals ORDER BY set_at DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None