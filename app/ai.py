import os, json, time, httpx, logging
from google import genai

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # Circuit Breaker state
        self.gemini_healthy = True
        self.last_error_time = 0
        self.retry_after = 60  # Error တက်ရင် စက္ကန့် ၆၀ စောင့်မယ်

    def _get_system_prompt(self, shop_name, menu):
        """SaaS dynamic system prompt with strict flow control"""
        return f"""
You are the professional AI Sales Executive for '{shop_name}'. 
Your primary job is to help customers place orders and collect their delivery details.

### CURRENT SHOP MENU & PRICE LIST:
{json.dumps(menu, indent=2)}

### OPERATIONAL GUIDELINES:
1. ONLY accept orders for items listed in the menu. If an item is out of stock, inform the user politely.
2. INFORMATION TO COLLECT:
   - Full Name
   - Phone Number
   - Delivery Address
   - Payment Method (COD or Preorder)
3. INTERACTION FLOW:
   - Step 1: Assist the user in selecting items and quantity.
   - Step 2: Once items are selected, gather Name, Phone, and Address.
   - Step 3: When ALL data is present, present a CLEAN SUMMARY and ask for "Confirm".
   - Step 4: ONLY when the user says "Confirm" or "Yes", set 'intent' to 'save_to_db'.

### OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "reply_text": "Your natural response in Myanmar language",
  "intent": "info_gathering" | "confirm_order" | "save_to_db",
  "order_summary": {{
      "name": "string", "phone": "string", "address": "string", 
      "items_text": "string", "total": number, "payment_type": "string"
  }},
  "final_order_data": {{
      "name": "string", "phone": "string", "address": "string",
      "items": [{{ "name": "string", "qty": number, "price": number }}],
      "total": number, "payment": "string"
  }}
}}
"""

    async def process_chat(self, user_text, chat_id, shop_name, menu):
        """Processing with Gemini-to-Groq Failover Logic"""
        system_prompt = self._get_system_prompt(shop_name, menu)
        
        # 1. Circuit Breaker Check
        current_time = time.time()
        if not self.gemini_healthy and (current_time - self.last_error_time < self.retry_after):
            logger.warning("⛓️ Circuit Breaker Active: Routing directly to Groq.")
            return await self.call_groq(system_prompt, user_text)

        # 2. Try Primary Model (Gemini 2.0 Flash)
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\nUser: {user_text}",
                config={"response_mime_type": "application/json"}
            )
            self.gemini_healthy = True
            logger.info("💎 Gemini processed successfully.")
            return json.loads(response.text)

        except Exception as e:
            logger.error(f"❌ Gemini Error: {e}")
            # Rate Limit သို့မဟုတ် 429 ဖြစ်ခဲ့လျှင် Switch လုပ်မည်
            if "429" in str(e) or "quota" in str(e).lower():
                self.gemini_healthy = False
                self.last_error_time = current_time
            
            # Switch to Groq
            return await self.call_groq(system_prompt, user_text)

    async def call_groq(self, system_prompt, user_text):
        """Secondary Model (Groq Llama 3.3) with JSON Object Mode"""
        logger.info("🌪️ Calling Groq Failover...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "You are a professional sales AI. Always output strict JSON."},
                            {"role": "user", "content": f"{system_prompt}\n\nUser Message: {user_text}"}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1 # စာသားတွေ မဖောက်ပြန်အောင် low temp ထားမယ်
                    },
                    timeout=15.0
                )
                content = resp.json()['choices'][0]['message']['content']
                return json.loads(content)
        except Exception as e:
            logger.error(f"❌ Failover Groq also failed: {e}")
            return {
                "reply_text": "စိတ်မရှိပါနဲ့ခင်ဗျာ၊ စနစ်အနည်းငယ် အလုပ်များနေလို့ပါ။ ခဏနေမှ ပြန်ပြောပေးပါဦး။",
                "intent": "info_gathering"
            }

ai_service = AIService()
