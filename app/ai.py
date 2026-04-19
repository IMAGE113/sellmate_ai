import os
import json
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
You are an AI sales assistant. Extract item name and quantity.
Return JSON ONLY:
{"intent": "order", "items": [{"name": "item_name", "qty": 1}]}
If the user is just greeting, return {"intent": "chat", "items": []}
"""

def parse_order(text: str):
    try:
        res = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=text,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        )
        return json.loads(res.text)
    except Exception:
        return {"intent": "chat", "items": []}
