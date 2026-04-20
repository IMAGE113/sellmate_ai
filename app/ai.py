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
        # အရင်မေးထားပြီးသား Data တွေကို ပြန်ယူမယ်
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
            
            # 🔥 BULLETPROOF MERGE: AI က Data ဖြုတ်ချန်ခဲ့ရင် အရင် Data ပြန်ဖြည့်ပေးမယ်
            merged_data = {
                "customer_name": new_final_data.get("customer_name") or prev_data.get("customer_name", ""),
                "phone_no": new_final_data.get("phone_no") or prev_data.get("phone_no", ""),
                "address": new_final_data.get("address") or prev_data.get("address", ""),
                "items": new_final_data.get("items") or prev_data.get("items", []),
                "total_price": new_final_data.get("total_price") or prev_data.get("total_price", 0)
            }

            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": merged_data
            }
        except Exception as e:
            print(f"Parse Error: {e}")
            return {"reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ပါ။", "intent": "info_gathering", "final_order_data": prev_data}

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", an expert Myanmar shop assistant for "{shop}".

[RULES]
1. ONLY suggest items from [SHOP MENU].
2. If user selects items, check [HISTORY].
   - If "customer_name" is empty, ask for name (e.g., "အမည်လေး သိပါရစေဗျာ").
   - If "customer_name" exists but "phone_no" is empty, ask for phone number.
   - If both exist but "address" is empty, ask for address.
3. NEVER ask for information that is already in [HISTORY].
4. Keep your Myanmar language very short, simple, polite and natural (Use 'ဗျာ' or 'ခင်ဗျာ'). Do NOT output weird translated sentences.
5. If all info (Name, Phone, Address, Items) is fully collected, reply "အော်ဒါ အကျဉ်းချုပ်လေးပါဗျာ" and set intent to "confirm_order".

[HISTORY]
{history}

[SHOP MENU]
{menu}

[OUTPUT FORMAT - JSON ONLY]
{{
 "reply_text": "Short Myanmar text reply",
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
