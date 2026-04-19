import os, json, time, httpx, logging
from google import genai

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.gemini_healthy = True
        self.last_error_time = 0
        self.retry_after = 60 

    def _get_system_prompt(self, shop_name, menu):
        # Menu ရှိမရှိ စစ်ပြီး Prompt ကို ပြောင်းလဲပေးမယ်
        menu_status = json.dumps(menu, ensure_ascii=False, indent=2) if menu else "လက်ရှိတွင် ရောင်းချရန် Menu မရှိသေးပါ။"
        
        return f"""
You are the professional AI Sales Executive for '{shop_name}'. 
Your primary goal is to take orders in Myanmar language beautifully and accurately.

### CURRENT SHOP MENU:
{menu_status}

### OPERATIONAL RULES (STRICT):
1. Respond in natural, polite Myanmar language (Zawgyi/Unicode friendly).
2. If the menu is empty, say: "မင်္ဂလာပါခင်ဗျာ။ လက်ရှိမှာတော့ ကျွန်တော်တို့ဆိုင်ရဲ့ Menu စာရင်းကို Dashboard မှာ မထည့်ရသေးလို့ မှာယူလို့မရသေးပါဘူးခင်ဗျာ။"
3. If menu exists, guide the user to select items, then ask for Name, Phone, and Address.
4. When all info is ready, present a summary and ask for "Confirm".
5. ONLY when the user says "Confirm", set 'intent' to 'save_to_db'.

### OUTPUT FORMAT (STRICT JSON):
{{
  "reply_text": "မြန်မာလို စာသားအမှန် (e.g. 'မင်္ဂလာပါ၊ ဘာမှာယူမလဲခင်ဗျာ')",
  "intent": "info_gathering" | "confirm_order" | "save_to_db",
  "order_summary": {{ "name": "...", "phone": "...", "address": "...", "items_text": "...", "total": 0, "payment_type": "..." }},
  "final_order_data": {{ "name": "...", "phone": "...", "address": "...", "items": [], "total": 0, "payment": "..." }}
}}
"""

    async def process_chat(self, user_text, chat_id, shop_name, menu):
        system_prompt = self._get_system_prompt(shop_name, menu)
        
        current_time = time.time()
        if not self.gemini_healthy and (current_time - self.last_error_time < self.retry_after):
            return await self.call_groq(system_prompt, user_text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            # ensure_ascii=False က မြန်မာစာကို ပိုပီသစေပါတယ်
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\nCustomer: {user_text}",
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
        logger.info("🌪️ Failover Routing: Groq active.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "You are a sales assistant. Always reply in beautiful Myanmar language and output strict JSON."},
                            {"role": "user", "content": f"{system_prompt}\n\nUser: {user_text}"}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2
                    },
                    timeout=15.0
                )
                return json.loads(resp.json()['choices'][0]['message']['content'])
        except Exception:
            return {"reply_text": "ခဏလေးစောင့်ပေးပါနော်။ စနစ်အနည်းငယ် အလုပ်များနေလို့ပါ။", "intent": "info_gathering"}

ai_service = AIService()
