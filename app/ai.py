import os, json, time, httpx, logging
from google import genai

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.gemini_healthy = True
        self.last_error_time = 0
        self.retry_after = 60 

    def _get_system_prompt(self, shop_name, menu):
        # Menu ကို စာသားအနေနဲ့ သေချာပြောင်းမယ်
        menu_str = ""
        for p in menu:
            menu_str += f"- {p['name']} ({p['price']} Ks)\n"

        return f"""
မင်းက '{shop_name}' ရဲ့ အရောင်းဝန်ထမ်း ဖြစ်တယ်။ 
စက်ရုပ်လို မဟုတ်ဘဲ လူတစ်ယောက်လို ယဉ်ကျေးပျူငှာစွာ မြန်မာလိုပဲ ပြောပါ။

### ဆိုင်၏ Menu:
{menu_str}

### လိုက်နာရန်:
၁။ အချက်အလက် (အမည်၊ ဖုန်း၊ လိပ်စာ) မပြည့်စုံခင်အထိ ပျူငှာစွာ မေးမြန်းပါ။
၂။ အကုန်စုံပြီဆိုလျှင် 'intent' ကို 'confirm_order' ဟု ပြောင်းပြီး မှာယူထားသည်များကို Summary ပြကာ အတည်ပြုခိုင်းပါ။
၃။ User က "Confirm/ဟုတ်ကဲ့/မှန်တယ်" ဟု ပြောမှသာ 'intent' ကို 'save_to_db' ဟု သတ်မှတ်ပါ။

### OUTPUT FORMAT (JSON ONLY):
{{
  "reply_text": "မြန်မာလို ပြန်ပြောမည့်စာ",
  "intent": "info_gathering" | "confirm_order" | "save_to_db",
  "order_summary": {{ "name": "...", "phone": "...", "address": "...", "items_text": "...", "total": 0 }},
  "final_order_data": {{ "name": "...", "phone": "...", "address": "...", "items": [], "total": 0 }}
}}
"""

    async def process_chat(self, user_text, chat_id, shop_name, menu):
        system_prompt = self._get_system_prompt(shop_name, menu)
        current_time = time.time()

        if not self.gemini_healthy and (current_time - self.last_error_time < self.retry_after):
            return await self.call_groq(system_prompt, user_text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\nCustomer: {user_text}",
                config={"response_mime_type": "application/json"}
            )
            self.gemini_healthy = True
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"❌ Gemini Error: {e}")
            self.gemini_healthy = False
            self.last_error_time = current_time
            return await self.call_groq(system_prompt, user_text)

    async def call_groq(self, system_prompt, user_text):
        logger.info("🌪️ Groq Failover active.")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "You are a polite Burmese sales assistant. Return JSON."},
                        {"role": "user", "content": f"{system_prompt}\n\nUser: {user_text}"}
                    ],
                    "response_format": {"type": "json_object"}
                }
            )
            return json.loads(resp.json()['choices'][0]['message']['content'])

ai_service = AIService()
