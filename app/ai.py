import os, json, asyncio, httpx, re
from google import genai
from google.genai import types

http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def safe_parse(self, text, history):
        try:
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
        except:
            return {"reply_text": "နားမလည်ပါဘူးခင်ဗျာ။", "intent": "info_gathering", "final_order_data": {}}

        final = data.get("final_order_data", {})

        return {
            "reply_text": data.get("reply_text", ""),
            "intent": data.get("intent", "info_gathering"),
            "final_order_data": {
                "customer_name": final.get("customer_name", ""),
                "phone_no": final.get("phone_no", ""),
                "address": final.get("address", ""),
                "payment_method": final.get("payment_method", "COD"),
                "items": final.get("items", [])
            }
        }

    def prompt(self, shop, menu):
        return f"""
You are a waiter for {shop}

STRICT RULE:
- ONLY use items from menu
- NEVER create new items

MENU:
{json.dumps(menu, ensure_ascii=False)}

Steps:
1 ask order
2 ask qty
3 ask name
4 ask phone
5 ask address
6 ask payment
7 confirm

Output JSON only
"""

    async def process(self, text, shop, menu, history="{}"):
        prompt = self.prompt(shop, menu)

        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "JSON only"},
                        {"role": "user", "content": prompt + f"\nUser: {text}"}
                    ],
                    "temperature": 0
                }
            )
            return self.safe_parse(res.json()['choices'][0]['message']['content'], history)

        except:
            return {"reply_text": "Server error", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
