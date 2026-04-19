import os
import json
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def parse_order(text: str):
    prompt = f"""
    You are a POS system. Your task is to extract items and quantities from user messages.
    
    Rules:
    1. If the user wants to buy/order any item (e.g., "Coffee 1", "Cola ၂ ဗူး"), set intent to "order".
    2. Extract product name and quantity (as integer).
    3. If the message is just a greeting or unrelated, set intent to "chat".
    4. MUST return ONLY a JSON object.

    User message: "{text}"

    JSON Format:
    {{
        "intent": "order",
        "items": [
            {{"name": "product_name", "qty": 1}}
        ]
    }}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"intent": "chat", "items": []}
