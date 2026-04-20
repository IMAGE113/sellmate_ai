import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

# Timeout ကို ၁၅ စက္ကန့်ထိ တိုးထားပေးပါတယ်
http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.gemini_ok = True
        self.last_fail = 0
        self.cooldown_period = 300  # 5 minutes cooldown

    def safe_parse(self, text):
        """AI ပြန်ပေးတဲ့ စာသားထဲကနေ JSON ကို သန့်သန့်လေး ဆွဲထုတ်မယ်"""
        try:
            text = re.sub(r"```json\s*|```", "", text).strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            
            data = json.loads(text)
            
            # Data Validation: အကယ်၍ data ထဲမှာ reply_text မပါရင် default စာထည့်မယ်
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
        # ဤနေရာတွင် logic ကို ပိုမိုတင်းကျပ်စွာ ရေးသားထားသည်
        return f"""
You are "SellMate AI", an expert Myanmar shop assistant for "{shop}". 

[GOAL]
Your goal is to collect Name, Phone, and Address for the order.

[STRICT INSTRUCTIONS TO AVOID LOOPS]
1. Read the [CURRENT DATA] carefully. 
2. If "customer_name" has a value, NEVER ask for the name again.
3. If "phone_no" has a value, NEVER ask for the phone number again.
4. If "address" has a value, NEVER ask for the address again.
5. ONLY ASK FOR ONE MISSING ITEM AT A TIME.

[CONVERSATION GUIDELINES]
- Speak in natural, friendly Myanmar "Spoken" style (e.g., "ဟုတ်ကဲ့ခင်ဗျာ", "ကျေးဇူးပြုပြီး... ပေးပါဦးဗျ")
- Do NOT use robotic or overly formal Burmese.
- If the user provides info, acknowledge it first, then ask for the next.

[SHOP MENU]
{menu}

[CURRENT DATA (FROM HISTORY)]
{history}

[OUTPUT FORMAT - ALWAYS RETURN JSON]
{{
 "reply_text": "Your natural Myanmar response",
 "intent": "info_gathering" (if still missing info) OR "confirm_order" (if all info exists),
 "final_order_data": {{
    "customer_name": "Update if provided",
    "phone_no": "Update if provided",
    "address": "Update if provided",
    "items": "Update based on user request",
    "total_price": "Calculate based on menu"
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        # History ထဲမှာ data မရှိရင် empty string ဖြစ်နေတတ်လို့ format ပြန်လုပ်မယ်
        if not history or history == "null":
            history = "{}"
            
        full_prompt = self.prompt(shop, menu, history)
        current_time = time.time()

        if not self.gemini_ok and (current_time - self.last_fail < self.cooldown_period):
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + f"\nUser Input: {text}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1 # ပိုတိကျအောင် temperature ကို ထပ်လျှော့ထားတယ်
                )
            )
            self.gemini_ok = True
            return self.safe_parse(res.text)

        except Exception as e:
            print(f"DEBUG: Gemini Error: {e}")
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
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
                    "messages": [
                        {"role": "system", "content": full_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            data = res.json()
            return self.safe_parse(data['choices'][0]['message']['content'])
        except Exception as e:
            print(f"DEBUG: Groq Error: {e}")
            return {"reply_text": "ခေတ္တစောင့်ဆိုင်းပေးပါခင်ဗျာ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
