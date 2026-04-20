import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

# Timeout ကို ၁၅ စက္ကန့်ထိ ထားရှိခြင်း
http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.gemini_ok = True
        self.last_fail = 0
        self.cooldown_period = 300 

    def safe_parse(self, text):
        """AI ပြန်ပေးတဲ့ စာသားထဲကနေ JSON ကို သန့်သန့်လေး ဆွဲထုတ်မယ်"""
        try:
            # Markdown code blocks များကို ဖယ်ထုတ်ခြင်း
            text = re.sub(r"```json\s*|```", "", text).strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            
            data = json.loads(text)
            
            # Default structure တည်ဆောက်ခြင်း
            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {
                    "customer_name": "",
                    "phone_no": "",
                    "address": "",
                    "items": [],
                    "total_price": 0
                })
            }
        except Exception as e:
            print(f"DEBUG: JSON Parse Error: {e}")
            return {
                "reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

    def prompt(self, shop, menu, history):
        # ဤနေရာတွင် Logic ကို အဆင့်ဆင့် စစ်ဆေးရန် ပြင်ဆင်ထားသည်
        return f"""
You are "SellMate AI", an expert Myanmar shop assistant for "{shop}". 

[STRICT PRIORITY RULES]
1. IF the user asks for something NOT in the [SHOP MENU] (e.g., Tea), politely say it's not available and suggest items from the menu.
2. IF the user mentions an item from the menu (e.g., Latte), confirm it and add to "items" immediately.
3. DO NOT ask for Customer Name, Phone, or Address until the user has chosen at least one valid item from the menu.
4. If "items" is empty, your ONLY goal is to help them choose from the menu.

[LOOP PREVENTION]
- Check [CURRENT DATA] (History) before asking any questions.
- If "customer_name" exists, DO NOT ask for it.
- If "phone_no" exists, DO NOT ask for it.
- If "address" exists, DO NOT ask for it.

[STYLE]
- Use natural spoken Myanmar (e.g., "ဟုတ်ကဲ့ခင်ဗျာ၊ Latte တစ်ခွက် မှတ်ထားပေးပါတယ်ဗျ။")
- Be concise. Don't repeat greeting.

[SHOP MENU]
{menu}

[CURRENT DATA (FROM HISTORY)]
{history}

[OUTPUT FORMAT - ALWAYS RETURN VALID JSON]
{{
 "reply_text": "Myanmar response",
 "intent": "info_gathering" OR "confirm_order",
 "final_order_data": {{
    "customer_name": "string",
    "phone_no": "string",
    "address": "string",
    "items": [{{ "name": "item_name", "qty": 1 }}],
    "total_price": 0
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        if not history or history == "null":
            history = "{}"
            
        full_prompt = self.prompt(shop, menu, history)
        current_time = time.time()

        # Cooldown logic for Gemini
        if not self.gemini_ok and (current_time - self.last_fail < self.cooldown_period):
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            # Gemini Prompting
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + f"\nUser Input: {text}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            self.gemini_ok = True
            return self.safe_parse(res.text)

        except Exception as e:
            print(f"DEBUG: Gemini Error: {e}")
            if any(err in str(e) for err in ["429", "RESOURCE_EXHAUSTED", "Quota"]):
                self.gemini_ok = False
                self.last_fail = current_time
            return await self.groq(full_prompt, text)

    async def groq(self, full_prompt, text):
        """Gemini အလုပ်မလုပ်ပါက Groq Llama-3 သို့ ပြောင်းသုံးခြင်း"""
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
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            data = res.json()
            if 'choices' in data:
                return self.safe_parse(data['choices'][0]['message']['content'])
            else:
                raise Exception(f"Groq API Error: {data}")
        except Exception as e:
            print(f"DEBUG: Groq Error: {e}")
            return {
                "reply_text": "ခေတ္တစောင့်ဆိုင်းပေးပါခင်ဗျာ။ စနစ်ပြင်ဆင်နေပါတယ်။", 
                "intent": "info_gathering", 
                "final_order_data": {}
            }

ai = AI()
