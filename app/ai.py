import os, json, asyncio, time, httpx, re
from google import genai

# Timeout ကို ၁၅ စက္ကန့်ထိ တိုးထားပေးပါတယ်
http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
        self.fail_count = 0
        self.gemini_ok = True
        self.last_fail = 0

    def safe_parse(self, text):
        """AI ပြန်ပေးတဲ့ စာသားထဲကနေ JSON block ကိုပဲ ဆွဲထုတ်ပေးမယ့် function"""
        try:
            # Markdown (```json ... ```) တွေကို ဖယ်ထုတ်ပြီး JSON string ကိုပဲ ယူမယ်
            text = re.sub(r"```json\s*|```", "", text).strip()
            
            # JSON block အစနဲ့အဆုံး ({ ... }) ကို ရှာမယ်
            start = text.find('{')
            end = text.rfind('}')
            
            if start != -1 and end != -1:
                text = text[start:end+1]
            
            data = json.loads(text)
            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": data.get("final_order_data", {})
            }
        except Exception as e:
            print(f"JSON Parse Error: {e}")
            return {
                "reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ ခဏနေမှ ပြန်ပြောပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": {}
            }

    def prompt(self, shop, menu, history):
        return f"""
You are "SellMate AI", a professional Myanmar shop assistant for "{shop}".
Task: Take orders and collect info (Name, Phone, Address).

[SHOP MENU]
{menu}

[CURRENT ORDER PROGRESS]
{history}

[RULES]
1. Use natural Myanmar spoken language (Friendly, "ခင်ဗျာ/ဗျ").
2. Update "final_order_data" as soon as you get info.
3. Set intent to "confirm_order" ONLY when all info is complete.
4. Output ONLY valid JSON.

[RESPONSE FORMAT]
{{
 "reply_text": "...",
 "intent": "info_gathering|confirm_order",
 "final_order_data": {{
    "customer_name": "...",
    "phone_no": "...",
    "address": "...",
    "items": [],
    "total_price": 0
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)

        # Gemini fail ဖြစ်ဖူးရင် ၅ မိနစ် (၃၀၀ စက္ကန့်) လောက် Groq ကိုပဲ တိုက်ရိုက်သုံးမယ်
        if not self.gemini_ok and (time.time() - self.last_fail < 300):
            print("--- Switch to Groq (Recovery Mode) ---")
            return await self.groq(full_prompt, text)

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=full_prompt + "\nUser said: " + text
            )
            self.fail_count = 0
            self.gemini_ok = True
            return self.safe_parse(res.text)

        except Exception as e:
            print(f"Gemini Error: {e}")
            self.fail_count += 1
            # တစ်ခါ fail တာနဲ့ Groq ကို ကူးမယ် (Free Tier Quota မြန်မြန်ကုန်တတ်လို့)
            self.gemini_ok = False
            self.last_fail = time.time()
            return await self.groq(full_prompt, text)

    async def groq(self, full_prompt, text):
        print("Groq is processing...")
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
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
            # Choices ကနေ content ကို ယူပြီး parse လုပ်မယ်
            content = data['choices'][0]['message']['content']
            return self.safe_parse(content)
        except Exception as e:
            print(f"Groq API Error: {e}")
            return {
                "reply_text": "⚠️ AI Offline (Both Gemini & Groq failed).",
                "intent": "info_gathering",
                "final_order_data": {}
            }

ai = AI()
