import os, json, asyncio, time, httpx
from google import genai

http_client = httpx.AsyncClient(timeout=10.0)

class AI:
    def __init__(self):
        self.fail_count = 0
        self.gemini_ok = True
        self.last_fail = 0

    def safe_parse(self, text):
        try:
            data = json.loads(text)
            return {
                "reply_text": data.get("reply_text", "Please try again."),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {"items": []})
            }
        except:
            return {
                "reply_text": "⚠️ System busy. Try again.",
                "intent": "info_gathering",
                "final_order_data": {"items": []}
            }

    def prompt(self, shop, menu):
        return f"""
You are SellMate AI for {shop}

MENU:
{menu}

RULES:
- Only use menu items EXACTLY
- Never guess price
- If unsure ask again

OUTPUT JSON:
{{
 "reply_text": "...",
 "intent": "info_gathering|confirm_order",
 "final_order_data": {{"name":"","phone":"","address":"","items":[],"total":0}}
}}
"""

    async def process(self, text, shop, menu):
        prompt = self.prompt(shop, menu)

        if not self.gemini_ok and time.time() - self.last_fail < 60:
            return await self.groq(prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            res = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model="gemini-2.0-flash",
                    contents=prompt + "\n" + text
                ),
                timeout=10
            )
            self.fail_count = 0
            return self.safe_parse(res.text)

        except:
            self.fail_count += 1
            if self.fail_count >= 3:
                self.gemini_ok = False
                self.last_fail = time.time()
            return await self.groq(prompt, text)

    async def groq(self, prompt, text):
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": prompt},
                                 {"role": "user", "content": text}],
                    "response_format": {"type": "json_object"}
                }
            )
            return self.safe_parse(res.json()['choices'][0]['message']['content'])
        except:
            return {
                "reply_text": "⚠️ AI offline. Try again.",
                "intent": "info_gathering",
                "final_order_data": {"items": []}
            }

ai = AI()
