import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.gemini_ok = True
        self.last_fail = 0
        self.cooldown_period = 300 

    def safe_parse(self, text):
        try:
            text = re.sub(r"```json\s*|```", "", text).strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            data = json.loads(text)
            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {
                    "customer_name": "", "phone_no": "", "address": "", "items": [], "total_price": 0
                })
            }
        except Exception:
            return {"reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ပါ။ ခဏနေမှ ပြန်ပြောပေးပါဗျာ။", "intent": "info_gathering", "final_order_data": {}}

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", an expert Myanmar shop assistant for "{shop}".
Your goal is to collect order details politely in Myanmar language.

[RULES]
1. ONLY suggest items from [SHOP MENU].
2. DO NOT ask for personal info (Name/Phone) until the user has chosen at least one valid item.
3. Check [HISTORY] before asking. If a field is already filled, NEVER ask it again.
4. Collect missing info one by one: Items -> Name -> Phone -> Address.
5. Use "ရှင့်" or "ဗျာ" based on shop style (Currently using male polite "ဗျာ").

[SHOP MENU]
{menu}

[CURRENT PROGRESS (HISTORY)]
{history}

[RESPONSE EXAMPLES]
- User wants item: "ဟုတ်ကဲ့ဗျာ၊ {shop} ကနေ ကြိုဆိုပါတယ်။ ဘယ်နှခွက် (သို့) ဘယ်နှစ်ခု ယူမလဲဗျာ?"
- Missing Name: "အော်ဒါအတွက် အမည်လေး သိပါရစေခင်ဗျာ။"
- All Collected: "အော်ဒါ အကျဉ်းချုပ်လေးပါဗျာ။ အကုန်မှန်တယ်ဆိုရင် 'Confirm' လို့ ပို့ပေးပါဦး။"

[OUTPUT FORMAT - JSON ONLY]
{{
 "reply_text": "မြန်မာလိုပြန်စာ",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "...", 
    "phone_no": "...", 
    "address": "...", 
    "items": [{{ "name": "...", "qty": 1, "price": 0 }}],
    "total_price": 0
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        current_time = time.time()

        # Check if Gemini is in cooldown
        if not self.gemini_ok and (current_time - self.last_fail < self.cooldown_period):
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            # Run in thread to avoid blocking
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + f"\nUser input: {text}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            self.gemini_ok = True
            return self.safe_parse(res.text)
        except Exception as e:
            if "429" in str(e):
                self.gemini_ok = False
                self.last_fail = current_time
                print("Gemini Rate Limit Hit - Switching to Groq")
            return await self.groq(full_prompt, text)

    async def groq(self, full_prompt, text):
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": full_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                }
            )
            data = res.json()
            return self.safe_parse(data['choices'][0]['message']['content'])
        except Exception:
            return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဗျာ။ စနစ် ခေတ္တ အလုပ်ရှုပ်နေလို့ပါ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
