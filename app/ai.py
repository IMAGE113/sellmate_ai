import os
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def ask_gemini(text):
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=text
    )
    return response.text
