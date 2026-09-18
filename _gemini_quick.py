"""Quick Gemini test."""
import os
from dotenv import load_dotenv
load_dotenv(r"D:\Deshneta\.env")
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
note = "দুপুর ১টা থেকে ৩টা সোলার কম থাকবে"

resp = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=f'Interpret this note and return JSON: "{note}"',
    config={"response_mime_type": "application/json"},
)
print("RAW:", resp.text[:500])