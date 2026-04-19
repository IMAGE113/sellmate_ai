import os
import json
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
You are a sales assistant. Extract items and quantities from the user text.
Return JSON ONLY:
{"intent": "order", "items": [{"name": "item_name", "qty": 1}]}
If not an order, return {"intent": "chat", "items": []}
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
