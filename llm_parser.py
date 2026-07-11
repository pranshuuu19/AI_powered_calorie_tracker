"""
llm_parser.py

Handles the LLM API call and the prompt engineering that turns a natural-
language food description into structured nutrition data.

Uses Groq's API (free tier, no billing/card required) with Llama models.
Originally built against Gemini, but Gemini's free tier requires a linked
billing account even for the free quota — Groq doesn't, so this project
uses Groq instead.

The parsing/validation logic is factored into `_parse_response_text()` on
purpose, separate from the actual network call in `parse_food_description()`.
This makes the parsing logic unit-testable without needing a live API key or
network access.
"""

import os
import json

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

PROMPT_TEMPLATE = """You are a nutrition estimation assistant. The user will describe what they ate in natural language (casual phrasing, multiple items in one sentence is fine).

Break the description down into individual food items, and for EACH item estimate:
- food_item: a short clean name for the item
- calories: estimated calories (number only)
- protein_g: estimated protein in grams (number only)
- carbs_g: estimated carbohydrates in grams (number only)
- fat_g: estimated fat in grams (number only)

Use standard reasonable portion sizes when the user doesn't specify quantity.

Respond with ONLY valid JSON, no markdown fences, no extra text, in this exact structure:
{{
  "items": [
    {{"food_item": "...", "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}}
  ]
}}

User's food description: "{user_input}"
"""

REQUIRED_KEYS = {"food_item", "calories", "protein_g", "carbs_g", "fat_g"}

_client = None  # module-level client, set by configure()


class ParseError(Exception):
    """Raised when the model's response can't be parsed into the expected structure."""
    pass


def configure(api_key: str):
    """Configure the Groq client. Imports groq lazily so this module can be
    imported (and its parsing logic tested) even in environments without the
    package installed or without network access.
    """
    global _client
    from groq import Groq
    _client = Groq(api_key=api_key)


def _parse_response_text(raw_text: str) -> list:
    """
    Pure parsing/validation function — no network calls. Takes the raw text
    a model returned and turns it into a validated list of food item dicts,
    or raises ParseError with a clear message.
    """
    raw_text = raw_text.strip()

    # Defensive cleanup in case the model wraps output in markdown fences anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ParseError(f"Model did not return valid JSON: {e}\nRaw response: {raw_text}")

    items = parsed.get("items")
    if not items or not isinstance(items, list):
        raise ParseError(f"Response JSON missing a non-empty 'items' list: {raw_text}")

    for item in items:
        missing = REQUIRED_KEYS - item.keys()
        if missing:
            raise ParseError(f"Item missing required keys {missing}: {item}")
        for numeric_key in ["calories", "protein_g", "carbs_g", "fat_g"]:
            if not isinstance(item[numeric_key], (int, float)):
                raise ParseError(f"'{numeric_key}' must be numeric, got {item[numeric_key]!r} in {item}")

    return items


def parse_food_description(user_input: str) -> list:
    """
    Sends the user's natural-language food description to the LLM and
    returns a validated list of structured food item dicts. Raises
    ParseError if the response can't be parsed into the expected structure.
    """
    if _client is None:
        raise RuntimeError("llm_parser.configure(api_key) must be called before parse_food_description().")

    prompt = PROMPT_TEMPLATE.format(user_input=user_input)
    response = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return _parse_response_text(response.choices[0].message.content)