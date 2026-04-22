import os, json, httpx, re

http_client = httpx.AsyncClient(timeout=15.0)

class AI:

    def safe_parse(self, text, history):
        try:
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
        except:
            return {
                "reply_text": "နားမလည်ပါဘူးခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

        final = data.get("final_order_data", {})

        return {
            "reply_text": data.get("reply_text") or "ဘာများ မှာယူမလဲခင်ဗျာ?",
            "intent": data.get("intent", "info_gathering"),
            "final_order_data": {
                "customer_name": final.get("customer_name", ""),
                "phone_no": final.get("phone_no", ""),
                "address": final.get("address", ""),
                "payment_method": final.get("payment_method", "COD"),
                "items": final.get("items", [])
            }
        }

    def prompt(self, shop, menu, current_order):
        return f"""
You are a professional waiter for {shop}

CURRENT ORDER:
{json.dumps(current_order, ensure_ascii=False)}

MENU:
{json.dumps(menu, ensure_ascii=False)}

STRICT RULES:
- Reply ONLY in natural Myanmar language
- Use "ခင်ဗျာ"
- ONLY use items from MENU
- NEVER invent items
- Maintain CURRENT ORDER (do not reset)

FLOW:
1 ask order
2 ask qty
3 ask name
4 ask phone
5 ask address
6 ask payment (COD/Prepaid)
7 confirm

OUTPUT JSON ONLY:
{{
 "reply_text": "...",
 "intent": "info_gathering or confirm_order",
 "final_order_data": {{
   "customer_name": "",
   "phone_no": "",
   "address": "",
   "payment_method": "COD",
   "items": [{{"name": "", "qty": 1}}]
 }}
}}
"""

    async def process(self, text, shop, menu, current_order):
        prompt = self.prompt(shop, menu, current_order)

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
            return self.safe_parse(res.json()['choices'][0]['message']['content'], current_order)

        except:
            return {
                "reply_text": "Server error ခဏနေပြန်ကြိုးစားပါခင်ဗျာ",
                "intent": "info_gathering",
                "final_order_data": {}
            }

ai = AI()
