"""
test_groq.py — standalone diagnostic script.

Run this directly (not through Streamlit) to isolate whether a Groq API
call succeeds, fails clearly, or hangs — same idea as the earlier Gemini
diagnostic, adapted for Groq.

Usage:
    python test_groq.py
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GROQ_API_KEY")
model_name = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

print(f"GROQ_API_KEY loaded: {'YES (' + api_key[:6] + '...)' if api_key else 'NO — .env not found or key missing'}")
print(f"GROQ_MODEL: {model_name}")

if not api_key:
    print("\n❌ Stopping — no API key found. Check your .env file exists and has GROQ_API_KEY set.")
    sys.exit(1)

print("\nImporting groq...")
try:
    from groq import Groq
    print("✓ Import succeeded")
except Exception as e:
    print(f"❌ Import failed: {e}")
    print("   Try: pip install groq")
    sys.exit(1)

print("\nCreating client...")
try:
    client = Groq(api_key=api_key)
    print("✓ Client created")
except Exception as e:
    print(f"❌ Client creation failed: {e}")
    sys.exit(1)

print(f"\nListing available models (this also tests network connectivity)...")
try:
    start = time.time()
    models = client.models.list()
    elapsed = time.time() - start
    model_ids = [m.id for m in models.data]
    print(f"✓ Reached the API in {elapsed:.1f}s — {len(model_ids)} models available")
    if model_name not in model_ids:
        print(f"  ⚠️  Your configured model '{model_name}' was not found. Available models:")
        print(f"     {model_ids}")
    else:
        print(f"  ✓ '{model_name}' is available")
except Exception as e:
    print(f"❌ Could not reach the API / list models: {e}")
    sys.exit(1)

print(f"\nSending a real test prompt to '{model_name}'...")
try:
    start = time.time()
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
    )
    elapsed = time.time() - start
    print(f"✓ Got a response in {elapsed:.1f}s:")
    print(f"  {response.choices[0].message.content!r}")
except Exception as e:
    print(f"❌ Chat completion failed: {e}")
    sys.exit(1)

print("\n✅ Everything works. If the Streamlit app still hangs, the problem is Streamlit-specific, not the Groq API itself.")