import os
import json
import logging
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Manual Override အတွက် မြန်မာ Keyword များ
ORDER_KEYWORDS = ["ယူမယ်", "ဝယ်မယ်", "လိုချင်", "ပေးပါ", "မှာမယ်", "ရမလား", "ခွက်", "ဗူး", "ထုပ်", "ထုတ်"]

def parse_order(text: str):
    # Keyword ပါမပါ အရင်စစ်မယ်
    is_likely_order = any(k in text for k in ORDER_KEYWORDS)
    
    system_prompt = """
    You are SellMate POS AI.
    - If user mentions any product name or quantity, intent MUST be 'order'.
    - Convert Burmese numbers to English integers.
    - Return ONLY valid JSON.
    Format: {"intent": "order/chat", "items": [{"name": "...", "qty": 1}]}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{system_prompt}\n\nUser text: '{text}'",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        result = json.loads(response.text)
        
        # Hybrid Fix: AI က chat လို့ မှားရင်တောင် Keyword ပါရင် Order အဖြစ် ပြောင်းမယ်
        if result.get("intent") == "chat" and is_likely_order:
            logger.info(f"Hybrid Engine Triggered: Overriding intent for '{text}'")
            result["intent"] = "order"
            
        logger.info(f"AI OUTPUT: {result}")
        return result

    except Exception as e:
        logger.error(f"AI ERROR: {e}")
        return {"intent": "chat", "items": []}
