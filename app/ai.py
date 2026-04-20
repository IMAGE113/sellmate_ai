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
            prev_data = json.loads(history_str) if history_str else {}
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
            
            # Data Merge: အချက်အလက်အသစ်နဲ့ အဟောင်းကို ပေါင်းစပ်ပေးမယ်
            merged_data = {
                "customer_name": new_final_data.get("customer_name") or prev_data.get("customer_name", ""),
                "phone_no": new_final_data.get("phone_no") or prev_data.get("phone_no", ""),
                "address": new_final_data.get("address") or prev_data.get("address", ""),
                "payment_method": new_final_data.get("payment_method") or prev_data.get("payment_method", ""),
                "items": new_final_data.get("items") or prev_data.get("items", []),
                "total_price": new_final_data.get("total_price") or prev_data.get("total_price", 0)
            }

            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": merged_data
            }
        except Exception as e:
            return {"reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ပါ။", "intent": "info_gathering", "final_order_data": prev_data}

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", a professional waiter for "{shop}". 
Tone: Polite Myanmar language ("ဗျာ/ခင်ဗျာ").

[OBJECTIVE]
Collect these details ONE BY ONE:
1. Items & Quantity (Confirm what they want first)
2. Customer Name
3. Phone Number
4. Address
5. Payment Method (COD or Pre-paid)

[STRICT RULES]
- If User says "ဒါပဲ" or "ရပြီ", move to the next step (Name/Phone/Address).
- If Payment is "Pre-paid", tell user to send payment proof to Admin after the summary.
- ONLY ask for info that is missing in [HISTORY].
- DO NOT translate product names from [MENU]. Use them as they are.

[HISTORY]
{history}

[MENU]
{menu}

[OUTPUT FORMAT - JSON ONLY]
{{
 "reply_text": "မြန်မာလို ယဉ်ကျေးစွာ ပြန်စာ",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "...", 
    "phone_no": "...", 
    "address": "...",
    "payment_method": "COD" or "Pre-paid",
    "items": [{{ "name": "...", "qty": 1, "price": 0 }}]
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
            self.gemini_ok = False
            self.last_fail = current_time
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
            return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဗျာ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
