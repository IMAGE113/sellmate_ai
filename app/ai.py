import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

# Global HTTP Client for Groq API
http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        # API Status Tracking
        self.groq_ok = True
        self.gemini_ok = True
        self.last_groq_fail = 0
        self.last_gemini_fail = 0
        self.cooldown = 300 

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
            
            merged_data = {
                "customer_name": new_final_data.get("customer_name") or prev_data.get("customer_name", ""),
                "phone_no": new_final_data.get("phone_no") or prev_data.get("phone_no", ""),
                "address": new_final_data.get("address") or prev_data.get("address", ""),
                "payment_method": new_final_data.get("payment_method") or prev_data.get("payment_method", ""),
                "items": new_final_data.get("items") if new_final_data.get("items") else prev_data.get("items", []),
                "total_price": 0 
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
[SYSTEM ROLE]
You are a highly efficient Order-Taking Assistant for "{shop}". 
Your ONLY goal is to extract order details into a structured JSON format. 
Language: Myanmar (Polite, using ဗျာ/ခင်ဗျာ).

[SHOP MENU - ONLY RECOMMEND THESE]
{menu}

[ORDER GATHERING RULES - CRITICAL]
1. CHECK HISTORY: Do not ask for information already present in [HISTORY].
2. ONE AT A TIME: Ask for missing details one by one.
3. MENU ONLY: If a user orders something NOT in the menu, politely say it's unavailable.
4. CONFIRMATION: Once ALL details are collected, set "intent" to "confirm_order".
5. RESET: If user says "clear", "cancel", "အကုန်ဖျက်", or "ပြန်မှာမယ်", return empty fields.

[CURRENT HISTORY]
{history}

[REQUIRED FIELDS]
- items: List of objects with "name" and "qty".
- customer_name, phone_no, address, payment_method.

[OUTPUT INSTRUCTION]
Respond ONLY with a valid JSON object.

{{
 "reply_text": "Your response in Myanmar",
 "intent": "info_gathering" OR "confirm_order",
 "final_order_data": {{
    "customer_name": "...", 
    "phone_no": "...", 
    "address": "...",
    "payment_method": "COD" or "Pre-paid",
    "items": [{{ "name": "...", "qty": 1 }}]
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        now = time.time()

        # 1. Try Groq (Primary)
        if self.groq_ok or (now - self.last_groq_fail > self.cooldown):
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
                if res.status_code == 200:
                    self.groq_ok = True
                    return self.safe_parse(res.json()['choices'][0]['message']['content'], history)
                else:
                    raise Exception(f"Groq Error: {res.status_code}")
            except Exception as e:
                print(f"Groq Failed: {e}")
                self.groq_ok = False
                self.last_groq_fail = now

        # 2. Try Gemini (Backup)
        if self.gemini_ok or (now - self.last_gemini_fail > self.cooldown):
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
                print(f"Gemini Backup Failed: {e}")
                self.gemini_ok = False
                self.last_gemini_fail = now

        return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဗျာ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
