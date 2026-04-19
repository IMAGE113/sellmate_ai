import os, json, time, httpx, logging
from google import genai

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.gemini_healthy = True
        self.last_error_time = 0
        self.retry_after = 60 

    def _get_system_prompt(self, shop_name, menu):
        menu_json = json.dumps(menu, ensure_ascii=False)
        return f"""
မင်းက '{shop_name}' ဆိုင်ရဲ့ လူမှုရေးပြေပြစ်တဲ့ အရောင်းဝန်ထမ်း ဖြစ်တယ်။ 
Customer နဲ့ စကားပြောတဲ့အခါ စက်ရုပ်လိုမဟုတ်ဘဲ နွေးထွေးတဲ့ အရောင်းဝန်ထမ်းတစ်ယောက်လို မြန်မာလို ယဉ်ကျေးစွာ ပြောပေးပါ။

### ဆိုင်၏ Menu စာရင်း:
{menu_json}

### လိုက်နာရမည့် အရောင်းအဆင့်ဆင့်:
၁။ **Greeting**: နှုတ်ဆက်ပြီး Menu ထဲက ဘာယူမလဲ မေးပါ။ (စကားလုံး ထပ်မနေပါစေနှင့်)။
၂။ **Selection**: User က ပစ္စည်းရွေးပြီးရင် "နာမည်၊ ဖုန်းနံပါတ်၊ လိပ်စာ" မေးပါ။ (စကားလုံး အပိုတွေ မသုံးပါနဲ့)။
၃။ **Summary**: အချက်အလက်စုံပြီဆိုတာနဲ့ 'intent' ကို 'confirm_order' လို့ ပြောင်းပါ။ reply_text မှာ "အော်ဒါလေး ပြန်စစ်ပေးပါဦး" ဆိုပြီး summary ကို သေချာပြပါ။
၄။ **Finalization**: User က "ဟုတ်ကဲ့/မှန်ပါတယ်/Confirm" လို့ ပြောမှသာ 'intent' ကို 'save_to_db' လို့ သတ်မှတ်ပါ။

### OUTPUT FORMAT (STRICT JSON):
{{
  "reply_text": "မြန်မာလို ယဉ်ကျေးသော ပြန်ကြားစာ",
  "intent": "info_gathering" | "confirm_order" | "save_to_db",
  "order_summary": {{
      "name": "အမည်",
      "phone": "ဖုန်း",
      "address": "လိပ်စာ",
      "items_text": "မှာယူသည့်ပစ္စည်းများ",
      "total": 0,
      "payment_type": "COD"
  }},
  "final_order_data": {{
      "name": "...", "phone": "...", "address": "...",
      "items": [], "total": 0, "payment": "COD"
  }}
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
                config={{"response_mime_type": "application/json"}}
            )
            self.gemini_healthy = True
            return json.loads(response.text)

        except Exception as e:
            logger.error(f"❌ Gemini Error: {{e}}")
            if "429" in str(e) or "quota" in str(e).lower():
                self.gemini_healthy = False
                self.last_error_time = current_time
            return await self.call_groq(system_prompt, user_text)

    async def call_groq(self, system_prompt, user_text):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={{"Authorization": f"Bearer {{os.getenv('GROQ_API_KEY')}} "}},
                    json={{
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {{"role": "system", "content": "You are a professional Burmese sales assistant. Output JSON."}},
                            {{"role": "user", "content": f"{{system_prompt}}\n\nUser: {{user_text}}"}}
                        ],
                        "response_format": {{"type": "json_object"}},
                        "temperature": 0.2
                    }}
                )
                return json.loads(resp.json()['choices'][0]['message']['content'])
        except:
            return {{"reply_text": "ခဏလေးနော်၊ စနစ်အနည်းငယ် အလုပ်များနေလို့ပါ။", "intent": "info_gathering"}}

ai_service = AIService()
