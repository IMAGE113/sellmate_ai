import os, json, time, httpx, logging
from google import genai

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # 🏥 Circuit Breaker States
        self.gemini_healthy = True
        self.last_error_time = 0
        self.retry_after = 60 

    def _get_system_prompt(self, shop_name, menu):
        return f"""
မင်းက '{shop_name}' ရဲ့ Professional AI Sales ဝန်ထမ်း ဖြစ်တယ်။ 

### လက်ရှိရောင်းချနေသော Menu:
{json.dumps(menu, indent=2)}

### မဖြစ်မနေ လိုက်နာရန်:
၁။ အမည်၊ ဖုန်း၊ လိပ်စာ၊ မှာယူမည့်ပစ္စည်း နှင့် ငွေပေးချေမှုပုံစံ (COD/Preorder) ကို မေးပါ။
၂။ အချက်အလက်စုံပြီဆိုလျှင် အော်ဒါအနှစ်ချုပ် (Summary) ကိုပြပြီး User ကို "Confirm" လုပ်ခိုင်းပါ။
၃။ User က "Confirm" သို့မဟုတ် "ဟုတ်ကဲ့/မှန်တယ်" ဟု ပြောမှသာ 'intent' ကို 'save_to_db' ဟု သတ်မှတ်ပါ။

### OUTPUT FORMAT (JSON ONLY):
{{
  "reply_text": "မြန်မာလို ယဉ်ကျေးစွာ ပြန်ပြောမည့်စာ",
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
        system_prompt = self._get_system_prompt(shop_name, menu)
        
        # 🏥 1. Health Check
        current_time = time.time()
        if not self.gemini_healthy and (current_time - self.last_error_time < self.retry_after):
            logger.warning("⛓️ Gemini is cooling down. Routing to Groq...")
            return await self.call_groq(system_prompt, user_text)

        # 🚀 2. Try Gemini
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\nUser: {user_text}",
                config={"response_mime_type": "application/json"}
            )
            self.gemini_healthy = True
            return json.loads(response.text)

        except Exception as e:
            logger.error(f"❌ Gemini Error: {e}")
            if "429" in str(e) or "quota" in str(e).lower():
                self.gemini_healthy = False
                self.last_error_time = current_time
            return await self.call_groq(system_prompt, user_text)

    async def call_groq(self, system_prompt, user_text):
        """Failover to Groq Llama 3.3"""
        logger.info("🌪️ Failover Routing: Groq active.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "You are a sales AI. Output strict JSON."},
                            {"role": "user", "content": f"{system_prompt}\n\nUser: {user_text}"}
                        ],
                        "response_format": {"type": "json_object"}
                    },
                    timeout=15.0
                )
                return json.loads(resp.json()['choices'][0]['message']['content'])
        except Exception:
            return {"reply_text": "စနစ်အနည်းငယ် အလုပ်များနေလို့ပါ။ ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။", "intent": "info_gathering"}

ai_service = AIService()
