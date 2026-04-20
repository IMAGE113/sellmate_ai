import os, json, asyncio, time, httpx, re
from google import genai
from google.genai import types

# Global HTTP Client
http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def __init__(self):
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
            # Clean JSON string from markdown
            text = re.sub(r"```json\s*|```", "", text).strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            
            data = json.loads(text)
            new_final_data = data.get("final_order_data", {})
            
            # Ensure items is always a list
            items = new_final_data.get("items", [])
            if not isinstance(items, list):
                items = []

            # Hard Constraint: Data merging logic
            merged_data = {
                "customer_name": str(new_final_data.get("customer_name") or prev_data.get("customer_name", ""))[:100],
                "phone_no": str(new_final_data.get("phone_no") or prev_data.get("phone_no", ""))[:20],
                "address": str(new_final_data.get("address") or prev_data.get("address", ""))[:255],
                "payment_method": new_final_data.get("payment_method") or prev_data.get("payment_method", "COD"),
                "items": items,
                "total_price": 0 
            }

            return {
                "reply_text": data.get("reply_text", "ဟုတ်ကဲ့ခင်ဗျာ၊ ဘာများ ထပ်ကူညီပေးရမလဲ?"),
                "intent": data.get("intent", "info_gathering"),
                "final_order_data": merged_data
            }
        except Exception:
            return {"reply_text": "စနစ် အနည်းငယ် အလုပ်ရှုပ်နေလို့ပါ။ ခေတ္တစောင့်ပေးပါခင်ဗျာ။", "intent": "info_gathering", "final_order_data": prev_data}

    def prompt(self, shop, menu, history):
        return f"""
# SYSTEM MANDATE (HARD RULES)
1. IDENTITY: You are an automated Waiter for "{shop}". 
2. OBJECTIVE: Follow these 7 steps strictly. Do not skip any step.
3. LANGUAGE: Natural Myanmar with "ဗျာ/ခင်ဗျာ". No robotic direct translations.
4. NO TRANSLATION: Use Menu names exactly (e.g., "Latte", "Espresso").

# ORDERING WORKFLOW (FOLLOW STEP-BY-STEP)
- Step 1: Welcome message & Ask "ဘာမှာယူချင်ပါလဲခင်ဗျာ?"
- Step 2: If item mentioned but no quantity, ask for Quantity.
- Step 3: Ask for Name "အော်ဒါတင်ဖို့အတွက် နာမည်လေး ဘယ်လိုခေါ်ရမလဲခင်ဗျာ?"
- Step 4: Ask for Phone Number "ဖုန်းနံပါတ်လေး ပေးပါဦးခင်ဗျာ။"
- Step 5: Ask for Address "နေရပ်လိပ်စာ အပြည့်အစုံလေး ပေးပါဦးခင်ဗျာ။"
- Step 6: Ask Payment Method "COD (ပစ္စည်းရောက်ငွေချေ) လား၊ ငွေကြိုရှင်း (Prepaid) လားခင်ဗျာ?"
- Step 7: (CRITICAL) Summarize all details and ask user to confirm. "အချက်အလက်တွေ မှန်ကန်တယ်ဆိုရင် 'Confirm' လို့ ပြောပေးပါခင်ဗျာ။"

# SPECIAL LOGIC
- If intent is "confirm_order": 
  - If Payment is COD -> Tell user: "အော်ဒါတင်လိုက်ပါပြီဗျာ။ ဒါကတော့ သင့်ရဲ့ Slip ပါ။"
  - If Payment is Prepaid -> Tell user: "ငွေလွှဲပြေစာ (Slip) ကို Admin ဆီ ပို့ပေးပါခင်ဗျာ။ Admin Confirm ပြီးတာနဲ့ အော်ဒါ တည်ဆောက်ပေးပါမည်။"

# SHOP DATA
Shop Name: {shop}
Menu: {menu}

# CONVERSATION HISTORY
{history}

# OUTPUT JSON FORMAT (MANDATORY)
{{
 "reply_text": "တိုတိုနှင့် လိုရင်း မြန်မာလို ပြန်စာ",
 "intent": "info_gathering" OR "confirm_order",
 "final_order_data": {{
    "customer_name": "...", 
    "phone_no": "...", 
    "address": "...",
    "payment_method": "COD or Prepaid",
    "items": [{{ "name": "...", "qty": 1 }}]
 }}
}}
"""

    async def process(self, text, shop, menu, history="{}"):
        full_prompt = self.prompt(shop, menu, history)
        now = time.time()

        # 1. Groq Logic (Primary)
        if self.groq_ok or (now - self.last_groq_fail > self.cooldown):
            try:
                res = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "You respond only in JSON format."},
                            {"role": "user", "content": full_prompt + f"\nUser Input: {text}"}
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code == 200:
                    self.groq_ok = True
                    return self.safe_parse(res.json()['choices'][0]['message']['content'], history)
                else:
                    raise Exception(f"Groq API Error: {res.status_code}")
            except Exception as e:
                print(f"Groq Error: {e}")
                self.groq_ok = False
                self.last_groq_fail = now

        # 2. Gemini Logic (Secondary Backup)
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
                print(f"Gemini Error: {e}")
                self.gemini_ok = False
                self.last_gemini_fail = now

        return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဗျာ။", "intent": "info_gathering", "final_order_data": {}}

ai = AI()
