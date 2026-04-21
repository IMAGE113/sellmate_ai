import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.groq_ok = True
        self.gemini_ok = True
        self.last_groq_fail = 0
        self.last_gemini_fail = 0
        self.cooldown = 120

    # ✅ SAFE PARSER (no crash + merge history)
    def safe_parse(self, text, history_str):
        try:
            prev_data = json.loads(history_str) if history_str else {}
        except:
            prev_data = {}

        try:
            text = re.sub(r"```json\s*|```", "", text).strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]

            data = json.loads(text)
            new_data = data.get("final_order_data", {})

            items = new_data.get("items", [])
            if not isinstance(items, list):
                items = []

            merged = {
                "customer_name": new_data.get("customer_name") or prev_data.get("customer_name"),
                "phone_no": new_data.get("phone_no") or prev_data.get("phone_no"),
                "address": new_data.get("address") or prev_data.get("address"),
                "payment_method": new_data.get("payment_method") or prev_data.get("payment_method", "COD"),
                "items": items,
                "total_price": 0
            }

            return {
                "reply_text": data.get("reply_text", "ဘာများ မှာယူချင်ပါသလဲခင်ဗျာ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": merged
            }

        except:
            return {
                "reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေပါတယ်။ ထပ်ပြောပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": prev_data
            }

    # ✅ SMART PROMPT (no loop + no hallucination)
    def prompt(self, shop, menu, history):
        menu_str = "\n".join([f"- {m['name']} ({m['price']} MMK)" for m in menu])

        return f"""
You are a professional waiter for "{shop}".

RULES:
- Speak natural Myanmar (polite).
- ONLY use items from menu.
- NEVER create new items.
- If item not in menu → ask again.

FLOW:
- Collect missing info step by step.
- DO NOT ask again if already provided.

DATA TO COLLECT:
name, phone, address, payment_method, items

Menu:
{menu_str}

Conversation History:
{history}

OUTPUT JSON:
{{
 "reply_text": "short natural reply",
 "intent": "info_gathering" OR "confirm_order",
 "final_order_data": {{
    "customer_name": "...",
    "phone_no": "...",
    "address": "...",
    "payment_method": "COD or Prepaid",
    "items": [{{"name": "...", "qty": 1}}]
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        now = time.time()

        # ✅ GROQ FIRST
        if self.groq_ok or (now - self.last_groq_fail > self.cooldown):
            try:
                res = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "You respond only in JSON."},
                            {"role": "user", "content": full_prompt + f"\nUser: {text}"}
                        ],
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code == 200:
                    self.groq_ok = True
                    return self.safe_parse(res.json()['choices'][0]['message']['content'], history)
                else:
                    raise Exception("Groq failed")

            except Exception as e:
                print("Groq Error:", e)
                self.groq_ok = False
                self.last_groq_fail = now

        # ✅ GEMINI BACKUP
        if self.gemini_ok or (now - self.last_gemini_fail > self.cooldown):
            try:
                client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                res = await asyncio.to_thread(
                    client.models.generate_content,
                    model="gemini-2.0-flash",
                    contents=full_prompt + f"\nUser: {text}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )
                self.gemini_ok = True
                return self.safe_parse(res.text, history)

            except Exception as e:
                print("Gemini Error:", e)
                self.gemini_ok = False
                self.last_gemini_fail = now

        return {
            "reply_text": "ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။",
            "intent": "info_gathering",
            "final_order_data": {}
        }

ai = AI()
