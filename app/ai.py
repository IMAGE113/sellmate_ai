import os
import json
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
Extract order from text.

Return JSON only:
{
 "intent":"order|chat",
 "items":[{"name":"","qty":1}]
}

Examples:
"cola 2" → {"intent":"order","items":[{"name":"cola","qty":2}]}
"ကော်ဖီ ၃" → {"intent":"order","items":[{"name":"coffee","qty":3}]}
"""

def parse_order(text: str):
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2
            )
        )

        raw = res.text.strip()

        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        return json.loads(raw)

    except:
        return {"intent":"chat","items":[]}
