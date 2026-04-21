import os, json, asyncio, time, httpx, re

# Global HTTP Client
http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.groq_ok = True
        self.gemini_ok = True
        self.last_groq_fail = 0
        self.last_gemini_fail = 0
        self.cooldown = 300 

    # -----------------------------
    # 🔒 HARD MENU VALIDATION
    # -----------------------------
    def validate_items(self, ai_items, menu):
        valid = []
        for ai_item in ai_items:
            name = ai_item.get("name", "").lower()
            match = next((m for m in menu if m["name"].lower() == name), None)
            if match:
                qty = max(1, int(ai_item.get("qty", 1)))
                valid.append({
                    "name": match["name"],
                    "qty": qty,
                    "price": match["price"]
                })
        return valid

    # -----------------------------
    # 🧠 SAFE PARSER (ANTI-HALLUCINATION)
    # -----------------------------
    def safe_parse(self, text, history_str, menu):
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

            raw_items = new_data.get("items", [])
            if not isinstance(raw_items, list):
                raw_items = []

            # ✅ VALIDATE AGAINST MENU
            valid_items = self.validate_items(raw_items, menu)

            total = sum(i["qty"] * i["price"] for i in valid_items)

            merged = {
                "customer_name": str(new_data.get("customer_name") or prev_data.get("customer_name", ""))[:100],
                "phone_no": str(new_data.get("phone_no") or prev_data.get("phone_no", ""))[:20],
                "address": str(new_data.get("address") or prev_data.get("address", ""))[:255],
                "payment_method": new_data.get("payment_method") or prev_data.get("payment_method", "COD"),
                "items": valid_items,
                "total_price": total
            }

            # ❌ if AI tried invalid menu → reject
            if raw_items and not valid_items:
                return {
                    "reply_text": "တောင်းပန်ပါတယ်ခင်ဗျာ၊ ဒီပစ္စည်း Menu ထဲမှာမရှိပါဘူး။ Menu ထဲကသာ ရွေးချယ်ပေးပါ။",
                    "intent": "info_gathering",
                    "final_order_data": prev_data
                }

            return {
                "reply_text": data.get("reply_text", "ဘာများ မှာယူချင်ပါသလဲခင်ဗျာ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": merged
            }

        except Exception:
            return {
                "reply_text": "စနစ် အနည်းငယ် ပြဿနာရှိနေပါတယ်ခင်ဗျာ။ ထပ်မံပြောပေးပါ။",
                "intent": "info_gathering",
                "final_order_data": prev_data
            }

    # -----------------------------
    # 🧠 STRONG PROMPT
    # -----------------------------
    def prompt(self, shop, menu, history):
        return f"""
You are a professional waiter for "{shop}".

STRICT RULES:
- Only use items EXACTLY from menu
- If item not in menu → REJECT
- DO NOT guess
- DO NOT create items
- NEVER repeat same question

FLOW:
1. Ask item
2. Ask quantity
3. Ask name
4. Ask phone
5. Ask address
6. Ask payment
7. Confirm order

Menu:
{menu}

History:
{history}

Return JSON ONLY:
{{
 "reply_text": "...",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "...",
    "phone_no": "...",
    "address": "...",
    "payment_method": "...",
    "items": [{{"name": "...", "qty": 1}}]
 }}
}}
"""

    # -----------------------------
    # 🚀 MAIN PROCESS
    # -----------------------------
    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        now = time.time()

        # -------- GROQ --------
        if self.groq_ok or (now - self.last_groq_fail > self.cooldown):
            try:
                res = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "JSON only"},
                            {"role": "user", "content": full_prompt + f"\nUser: {text}"}
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code == 200:
                    self.groq_ok = True
                    return self.safe_parse(res.json()['choices'][0]['message']['content'], history, menu)
                else:
                    raise Exception()
            except:
                self.groq_ok = False
                self.last_groq_fail = now

        # -------- GEMINI --------
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + f"\nUser: {text}",
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            self.gemini_ok = True
            return self.safe_parse(res.text, history, menu)

        except:
            return {
                "reply_text": "ခဏနေမှ ပြန်ကြိုးစားပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

ai = AI()
