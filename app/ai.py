import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.gemini_ok = True
        self.last_fail = 0
        self.cooldown_period = 300 

    def safe_parse(self, text, history_str):
        try:
            prev_data = json.loads(history_str)
        except Exception:
            prev_data = {}

        try:
            text = re.sub(r"```json\s*|```", "", text).strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            data = json.loads(text)
            
            new_final_data = data.get("final_order_data", {})
            
            # 🔥 BULLETPROOF MERGE: Data တွေ ပြန်မပျောက်အောင် အရင် History နဲ့ ပေါင်းပေးခြင်း
            merged_data = {
                "customer_name": new_final_data.get("customer_name") or prev_data.get("customer_name", ""),
                "phone_no": new_final_data.get("phone_no") or prev_data.get("phone_no", ""),
                "address": new_final_data.get("address") or prev_data.get("address", ""),
                "items": new_final_data.get("items") or prev_data.get("items", []),
                "total_price": new_final_data.get("total_price") or prev_data.get("total_price", 0)
            }

            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ မှာယူချင်ပါသလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": merged_data
            }
        except Exception as e:
            print(f"Parse Error: {e}")
            return {"reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ပါ။", "intent": "info_gathering", "final_order_data": prev_data}

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", a professional virtual assistant for the shop "{shop}".
Your task is to take orders from customers in a natural, polite Myanmar tone. 

[STRICT RULES ON PRODUCT NAMES]
- DO NOT translate product names into Myanmar script. 
- ALWAYS keep product names in their ORIGINAL English form as provided in [SHOP MENU].
- Example: If the menu says "Latte", use "Latte". NEVER use "လက်တေး".

[CONVERSATION STYLE]
- First Greeting: "မင်္ဂလာပါဗျာ! {shop} က ကြိုဆိုပါတယ်။ ဒီနေ့ ဘာများ သုံးဆောင်မလဲခင်ဗျာ? ☕️"
- Be concise. Don't repeat greetings if the user is already talking about order.
- Politeness: Use "ဗျာ" or "ခင်ဗျာ" naturally. 
- Do not use formal robotic Myanmar. Avoid "ကျွန်ုပ်တို့" or "ကူညီနိုင်ပါစေ".

[ORDER LOGIC]
1. Check [SHOP MENU] for available items. 
2. If user hasn't chosen items, show menu with English names.
3. Once items are selected, check [HISTORY] and ask for missing details one by one (Name -> Phone -> Address).
4. If all info is present, set intent to "confirm_order".

[HISTORY]
{history}

[SHOP MENU]
{menu}

[OUTPUT FORMAT - JSON ONLY]
{{
 "reply_text": "Short Myanmar reply using English for product names",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "...", 
    "phone_no": "...", 
    "address": "...", 
    "items": [{{ "name": "English Product Name", "qty": 1, "price": 0 }}],
    "total_price": 0
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        current_time = time.time()

        if not self.gemini_ok and (current_time - self.last_fail < self.cooldown_period):
            return await self.groq(full_prompt, text, history)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + f"\nUser input: {text}",
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            self.gemini_ok = True
            return self.safe_parse(res.text, history)
        except Exception as e:
            if "429" in str(e):
                self.gemini_ok = False
                self.last_fail = current_time
                print("Gemini Limit Hit! Switched to Groq.")
            return await self.groq(full_prompt, text, history)

    async def groq(self, full_prompt, text, history):
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
            return self.safe_parse(data['choices'][0]['message']['content'], history)
        except Exception:
            return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
