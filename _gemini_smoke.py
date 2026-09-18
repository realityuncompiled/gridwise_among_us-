"""Smoke test for Gemini."""
import os
import sys
from dotenv import load_dotenv
load_dotenv(r"D:\Deshneta\.env")

key = os.getenv("GEMINI_API_KEY")
print("key loaded:", bool(key), "len:", len(key) if key else 0)

from google import genai
client = genai.Client(api_key=key)
try:
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Return JSON: {\"ok\": true}",
        config={"response_mime_type": "application/json"},
    )
    print("OK:", resp.text)
except Exception as e:
    print("ERR type:", type(e).__name__)
    print("ERR msg :", str(e)[:800])
    sys.exit(1)