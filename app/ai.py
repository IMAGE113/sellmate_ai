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
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {
                    "customer_name": "", "phone_no": "", "address": "", "items": [], "total_price": 0
                })
            }
        except Exception as e:
            return {"reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ပါ။", "intent": "info_gathering", "final_order_data": {}}

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", an expert Myanmar shop assistant for "{shop}".

[STRICT PRIORITY]
1. If the user wants to buy something NOT in the [SHOP MENU], politely say you don't have it.
2. DO NOT ask for Customer Name/Phone/Address if the user has not selected a valid item yet.
3. If valid items are selected, check [HISTORY]:
   - If Name is missing -> Ask for Name.
   - If Phone is missing -> Ask for Phone.
   - If Address is missing -> Ask for Address.
4. If ALL info (Name, Phone, Address, Items) is present, set intent to "confirm_order".

[HISTORY]
{history}

[SHOP MENU]
{menu}

[STYLE]
- Natural spoken Myanmar. Friendly.

[OUTPUT FORMAT - JSON ONLY]
{{
 "reply_text": "Myanmar text",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "...", "phone_no": "...", "address": "...", 
    "items": [{{ "name": "...", "qty": 1 }}], "total_price": 0
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        current_time = time.time()

        if not self.gemini_ok and (current_time - self.last_fail < self.cooldown_period):
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + f"\nUser: {text}",
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            self.gemini_ok = True
            return self.safe_parse(res.text)
        except Exception as e:
            if "429" in str(e):
                self.gemini_ok = False
                self.last_fail = current_time
            return await self.groq(full_prompt, text)

    async def groq(self, full_prompt, text):
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": full_prompt}, {"role": "user", "content": text}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            data = res.json()
            return self.safe_parse(data['choices'][0]['message']['content'])
        except:
            return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
