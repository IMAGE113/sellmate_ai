import os, json, asyncio, time, httpx
from google import genai

http_client = httpx.AsyncClient(timeout=10.0)

class AI:
    def __init__(self):
        self.fail_count = 0
        self.gemini_ok = True
        self.last_fail = 0

    def safe_parse(self, text):
        # AI က ပြန်ပေးတဲ့ JSON ထဲမှာ Markdown Tag တွေ (```json ...) ပါလာရင် ဖယ်ဖို့
        clean_text = text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(clean_text)
            return {
                "reply_text": data.get("reply_text", "ခဏနေ ပြန်ကြိုးစားပေးပါခင်ဗျာ။"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {})
            }
        except:
            return {
                "reply_text": "⚠️ စနစ် ခေတ္တအလုပ်ရှုပ်နေလို့ ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", a professional and polite Myanmar virtual assistant for "{shop}".
Your job is to take orders and collect customer information (Name, Phone, Address).

[SHOP MENU]
{menu}

[CURRENT ORDER PROGRESS]
This is what we already know about the customer's current order:
{history}

[RULES]
1. Identity: You are the assistant for {shop}.
2. Tone: Friendly, natural Myanmar spoken language (Burmese). Use "ခင်ဗျာ" or "ဗျ". 
3. Logic: 
   - If information is missing, ask politely.
   - If the user provides new info, update the "final_order_data".
   - Set intent to "confirm_order" ONLY when you have: Items, Name, Phone, and Address.
4. Accuracy: Use EXACT names and prices from the [SHOP MENU].

[RESPONSE FORMAT - JSON ONLY]
{{
 "reply_text": "Your polite Myanmar reply here",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
    "customer_name": "...",
    "phone_no": "...",
    "address": "...",
    "items": [ {{"name": "...", "qty": 1, "price": 0}} ],
    "total_price": 0
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        # history parameter ထည့်လိုက်တာက အရင်က မှာထားတာတွေကို AI သိစေဖို့ပါ
        full_prompt = self.prompt(shop, menu, history)

        if not self.gemini_ok and time.time() - self.last_fail < 60:
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            # Gemini 2.0 Flash is fast and good with Myanmar language
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + "\nUser said: " + text
            )
            self.fail_count = 0
            return self.safe_parse(res.text)

        except Exception as e:
            print(f"Gemini Error: {e}")
            self.fail_count += 1
            if self.fail_count >= 3:
                self.gemini_ok = False
                self.last_fail = time.time()
            return await self.groq(full_prompt, text)

    async def groq(self, full_prompt, text):
        try:
            res = await http_client.post(
                "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": full_prompt},
                        {"role": "user", "content": text}
                    ],
                    "response_format": {"type": "json_object"}
                }
            )
            data = res.json()
            return self.safe_parse(data['choices'][0]['message']['content'])
        except Exception as e:
            print(f"Groq Error: {e}")
            return {
                "reply_text": "⚠️ AI စနစ် ခေတ္တအော့ဖ်လိုင်း ဖြစ်နေပါတယ်။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

ai = AI()
