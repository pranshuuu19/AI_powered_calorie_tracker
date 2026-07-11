# 🍽️ AI Calorie & Nutrition Tracker

Log meals in natural language ("2 rotis, a bowl of dal, and a banana"), tagged by meal (Breakfast/Lunch/Snacks/Dinner), and have an LLM parse them into structured nutrition data — calories, protein, carbs, fat — persisted to SQLite and rolled up into per-meal totals, daily totals, and longer-term trends.

## How it works

```
Natural-language food description (tagged: Breakfast/Lunch/Snacks/Dinner)
        │
        ▼
Groq API — Llama model (structured JSON extraction via prompt engineering)
        │
        ▼
Validation layer (catches malformed/incomplete responses before they reach the database)
        │
        ▼
SQLite (logs, goals, water_logs tables)
        │
        ▼
Streamlit dashboard:
  - Per-meal + daily totals, 7-day rolling average
  - Hydration tracker + logging streak
  - Quick-add for repeat meals (no re-parse needed)
  - Gentle, non-judgmental nutrition nudges
  - Historical trends via Plotly
```

## Tech stack

Streamlit · Groq API (Llama models) · SQLite · Plotly · Pandas

## Why Groq instead of Gemini

This project originally targeted the Gemini API, but Gemini's free tier requires a linked billing account (a card on file) before *any* quota activates — a real blocker for anyone without one. Groq's free tier has no such requirement and is significantly faster (sub-second responses), so the LLM integration uses Groq's Llama models instead. The parsing/validation logic (`_parse_response_text`) is provider-agnostic, so swapping providers again in the future is a small, isolated change.

## Features

- **Natural-language meal logging**, tagged by meal type
- **Per-meal + daily nutrition totals**, compared against a configurable daily calorie goal
- **7-day rolling average** — smooths out single-day noise (e.g. an unusually heavy exam-week day) instead of treating every day as pass/fail
- **Quick-add** — re-log frequently repeated meals (useful for repetitive hostel/mess food) without another AI call
- **Hydration tracker** — simple daily glass/bottle counter
- **Logging streak** — rewards consistency of logging, deliberately not tied to weight or any diet outcome
- **Gentle nudges** — e.g. flags if protein looks low relative to other macros logged that day, with cheap suggestions (dal, eggs, paneer, curd); flags if no breakfast is logged by early afternoon. Both are informational, never alarmist.
- **Historical trends** — daily calories vs. goal, daily macros, and calories broken down by meal type over time

## Repo structure

```
calorie_tracker/
├── app.py              # Streamlit frontend
├── llm_parser.py        # Groq API call + prompt engineering + response validation
├── db.py                  # SQLite persistence layer (logs, goals, water)
├── test_groq.py            # Standalone diagnostic script (run outside Streamlit)
├── requirements.txt
├── .env.example              # Template — copy to .env and add your real key
├── .gitignore
└── data/                       # SQLite database lives here (gitignored)
```

## Setup

### 1. Get a free Groq API key

Go to [console.groq.com/keys](https://console.groq.com/keys), sign in, and create a free API key. No billing/card required.

### 2. Clone and install

```bash
git clone https://github.com/pranshuuu19/AI_powered_calorie_tracker.git
cd AI_powered_calorie_tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Add your API key

```bash
cp .env.example .env
```

Open `.env` and replace `your_api_key_here` with your real Groq API key.

### 4. (Optional) Verify the API connection before running the full app

```bash
python test_groq.py
```

This prints each step (key loaded, client created, models available, a real test prompt) so any connection issue is easy to diagnose in isolation.

### 5. Run it

```bash
streamlit run app.py
```

Open the local URL it prints (usually `http://localhost:8501`).

## Notes on the extraction logic

The LLM's response is validated before it ever reaches the database — malformed JSON, missing fields, or non-numeric values are caught in `llm_parser._parse_response_text()` and surfaced as a clear error in the UI (`ParseError`) rather than silently corrupting logged data or crashing the app. This function is unit-testable independently of the actual API call.

## Known limitations

- Calorie/macro estimates are the model's best guess from a text description — not a substitute for verified nutrition labels or a food database lookup.
- No user authentication — this is a single-user local tracker (one SQLite file per install).
- No portion-size disambiguation UI yet — if you don't specify quantity, the model assumes a standard serving.
- Deliberately does not track weight or BMI — for a student-facing wellness tool, keeping the focus on "what did I eat" rather than a weight trendline avoids reinforcing unhealthy fixation on a number.