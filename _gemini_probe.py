"""Probe Gemini verbose."""
import sys, time, json
from dotenv import load_dotenv
load_dotenv(r"D:\Deshneta\.env")
import os
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

for model in ["gemini-3.6-flash", "gemini-2.5-pro", "gemini-2.5-flash"]:
    print(f"\n--- trying {model} ---", flush=True)
    try:
        resp = client.models.generate_content(
            model=model,
            contents='Return JSON: {"ok": true}',
            config={"response_mime_type": "application/json"},
        )
        print("OK:", resp.text[:200], flush=True)
        sys.exit(0)
    except Exception as e:
        print("ERR:", type(e).__name__, str(e)[:300], flush=True)
        time.sleep(2)

print("\nAll failed.", flush=True)