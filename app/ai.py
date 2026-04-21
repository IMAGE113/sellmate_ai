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
        self.cooldown = 300 

    def safe_parse(self, text, history_json):
        try:
            prev = history_json if isinstance(history_json, dict) else {}
        except:
            prev = {}

        try:
            text = re.sub(r"```json|```", "", text).strip()
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                text = text[start:end+1]

            data = json.loads(text)
            new = data.get("final_order_data", {})

            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": {
                    "customer_name": new.get("customer_name") or prev.get("customer_name", ""),
                    "phone_no": new.get("phone_no") or prev.get("phone_no", ""),
                    "address": new.get("address") or prev.get("address", ""),
                    "payment_method": new.get("payment_method") or prev.get("payment_method", "COD"),
                    "items": new.get("items", [])
                }
            }
        except:
            return {
                "reply_text": "စနစ် error ဖြစ်နေပါတယ်",
                "intent": "info_gathering",
                "final_order_data": prev
            }

    def prompt(self, shop, menu_list, history):
        return f"""
You are waiter for "{shop}"

STRICT RULE:
- Only use items from this menu
- Do NOT create new items

MENU:
{json.dumps(menu_list)}

HISTORY:
{json.dumps(history)}

User will order step by step.

Return JSON only:
{{
 "reply_text": "...",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "",
    "phone_no": "",
    "address": "",
    "payment_method": "COD",
    "items": [{{"name":"", "qty":1}}]
 }}
}}
"""

    async def process(self, text, shop, menu_list, history):
        full_prompt = self.prompt(shop, menu_list, history)

        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Return JSON only"},
                        {"role": "user", "content": full_prompt + f"\nUser: {text}"}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            return self.safe_parse(res.json()['choices'][0]['message']['content'], history)

        except Exception as e:
            print("AI Error:", e)
            return {"reply_text": "ခဏစောင့်ပါ", "intent": "info_gathering", "final_order_data": history}

ai = AI()
