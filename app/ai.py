import os
import json
import logging
import httpx
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

ORDER_KEYWORDS = ["ယူမယ်", "ဝယ်မယ်", "လိုချင်", "ပေးပါ", "မှာမယ်", "ရမလား", "ခွက်", "ဗူး", "ထုပ်", "ထုတ်"]

def parse_order(text: str):
    is_likely_order = any(k in text for k in ORDER_KEYWORDS)
    
    # --- 1. Try Gemini ---
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Extract order from: {text}. Return ONLY JSON: {{'intent': 'order/chat', 'items': [{{'name': '', 'qty': 1}}]}}",
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
        )
        return json.loads(response.text)
    
    except Exception as e:
        logger.warning(f"Gemini Limit/Error: {e}. Trying Groq...")
        
        # --- 2. Try Groq (Llama 3 Backup) ---
        try:
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key:
                with httpx.Client() as client:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        json={
                            "model": "llama-3.3-70b-versatile",
                            "messages": [
                                {"role": "system", "content": "You are a POS extractor. Output ONLY JSON: {'intent': 'order', 'items': [{'name': '', 'qty': 1}]}"},
                                {"role": "user", "content": text}
                            ],
                            "response_format": {"type": "json_object"}
                        }
                    )
                    groq_res = resp.json()
                    return json.loads(groq_res['choices'][0]['message']['content'])
        except Exception as groq_err:
            logger.error(f"Groq failed: {groq_err}")

        # --- 3. Manual Fallback ---
        if is_likely_order:
            return {"intent": "order", "items": [{"name": text, "qty": 1}]}
            
        return {"intent": "chat", "items": []}
