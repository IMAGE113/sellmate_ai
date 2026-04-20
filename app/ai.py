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
            # Markdown code blocks တွေပါလာရင် ဖယ်မယ်
            text = re.sub(r"```json\s*|```", "", text).strip()
            
            # JSON block ({ ... }) ကိုပဲ ရှာယူမယ်
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            
            data = json.loads(text)
            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {})
            }
        except Exception as e:
            print(f"JSON Parse Error: {e}")
            return {
                "reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", a polite and professional Myanmar shop assistant for "{shop}". 

[STRICT RULES]
1. Answer in natural, spoken Myanmar language (friendly style). Use "ခင်ဗျာ/ဗျ".
2. Check the [SHOP MENU] carefully. If an item is NOT in the menu, tell them politely it's unavailable.
3. COLLECT INFO STEP-BY-STEP: Don't ask for everything at once. 
   - Ask for Name first.
   - Then Phone Number.
   - Then Delivery Address.
4. If "final_order_data" already has info from [HISTORY], don't ask for it again.
5. Set intent to "confirm_order" ONLY when you have Name, Phone, Address, and Items.

[SHOP MENU]
{menu}

[CONVERSATION HISTORY & DATA]
{history}

[OUTPUT FORMAT]
Return ONLY a valid JSON object. No extra text.
{{
 "reply_text": "မြန်မာလို ပြန်ပြောမည့်စာ",
 "intent": "info_gathering OR confirm_order",
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

        # Health Check: Gemini fail ဖြစ်ထားရင် cooldown ပြည့်မပြည့်စစ်မယ်
        if not self.gemini_ok and (current_time - self.last_fail < self.cooldown_period):
            print(f"--- Gemini Cooldown ({int(self.cooldown_period - (current_time - self.last_fail))}s left). Using Groq... ---")
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            # Gemini 2.0 Flash ကို JSON Mode တိုက်ရိုက်သုံးခိုင်းမယ် (စာပိုမှန်အောင်)
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + "\nUser: " + text,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2 # စာတွေ လျှောက်မထွင်အောင် လျှော့ထားတယ်
                )
            )
            self.gemini_ok = True
            return self.safe_parse(res.text)

        except Exception as e:
            err_msg = str(e)
            print(f"Gemini Error: {err_msg}")
            
            # Rate limit (429) မိတာသေချာရင် Cooldown စမယ်
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                self.gemini_ok = False
                self.last_fail = current_time
            
            return await self.groq(full_prompt, text)

    async def groq(self, full_prompt, text):
        print("Groq is processing...")
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GRO['API_KEY')}"},
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
            content = data['choices'][0]['message']['content']
            return self.safe_parse(content)
        except Exception as e:
            print(f"Groq API Error: {e}")
            return {
                "reply_text": "⚠️ ခဏလေးနော်၊ စနစ်အနည်းငယ် ပြဿနာတက်နေလို့ပါ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

ai = AI()
