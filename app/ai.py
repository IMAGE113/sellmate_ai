import os, json, httpx, re

http_client = httpx.AsyncClient(timeout=15.0)

class AI:
    def safe_parse(self, text, current_order):
        try:
            # Markdown block တွေကို ဖယ်ထုတ်ပြီး clean လုပ်တယ်
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
        except:
            # JSON parse မရရင် လက်ရှိ order data ကို မပျောက်အောင် ပြန်ပို့ပေးရမယ်
            return {
                "reply_text": "နားမလည်ပါဘူးခင်ဗျာ။ တစ်ချက်ပြန်ပြောပေးပါဦး။",
                "intent": "info_gathering",
                "final_order_data": current_order # Memory မပျောက်အောင် ထိန်းထားတယ်
            }

        ai_final = data.get("final_order_data", {})
        
        # UI/UX အတွက် Default စာသား
        reply = data.get("reply_text") or "ဘာများ မှာယူမလဲခင်ဗျာ?"
        intent = data.get("intent", "info_gathering")

        # CTO Fix: AI က logic လွဲပြီး empty ပို့လိုက်ရင်တောင် အရင်ရှိပြီးသား data မပျောက်အောင် merge လုပ်တယ်
        merged_order = {
            "customer_name": ai_final.get("customer_name") or current_order.get("customer_name", ""),
            "phone_no": ai_final.get("phone_no") or current_order.get("phone_no", ""),
            "address": ai_final.get("address") or current_order.get("address", ""),
            "payment_method": ai_final.get("payment_method") or current_order.get("payment_method", "COD"),
            "items": ai_final.get("items") if ai_final.get("items") else current_order.get("items", [])
        }

        return {
            "reply_text": reply,
            "intent": intent,
            "final_order_data": merged_order
        }

    def prompt(self, shop, menu, current_order):
        # Prompt ကို ပိုပြီး Force လုပ်ထားတယ် (Hallucination ကာကွယ်ဖို့)
        return f"""
You are the AI head waiter for {shop}. 
Reply ONLY in Myanmar language. 
Always use "ခင်ဗျာ".

[MENU JSON]
{json.dumps(menu, ensure_ascii=False)}

[CURRENT STATE]
{json.dumps(current_order, ensure_ascii=False)}

[STRICT INSTRUCTIONS]
1. If item is NOT in Menu, politely say we don't have it.
2. Update the CURRENT STATE with new info from the user.
3. Don't ask for info already present in CURRENT STATE.
4. If all info is present, set intent to "confirm_order".

[STRICT FLOW]
- Items & Qty -> Name -> Phone -> Address -> Payment -> Confirm.

[OUTPUT FORMAT]
Return ONLY JSON.
{{
 "reply_text": "your response in Myanmar",
 "intent": "info_gathering" or "confirm_order",
 "final_order_data": {{
   "customer_name": "string",
   "phone_no": "string",
   "address": "string",
   "payment_method": "COD or Prepaid",
   "items": [{"name": "item_name", "qty": 1}]
 }}
}}
"""

    async def process(self, text, shop, menu, current_order):
        full_prompt = self.prompt(shop, menu, current_order)

        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "You are a specialized ordering system that outputs STRICT JSON only."},
                        {"role": "user", "content": f"{full_prompt}\n\nUser Input: {text}"}
                    ],
                    "temperature": 0,
                    # Groq မှာ JSON Mode ကို Force လုပ်လိုက်တာ (အရေးကြီးတယ်)
                    "response_format": {"type": "json_object"} 
                }
            )
            
            if res.status_code != 200:
                raise Exception(f"Groq API Error: {res.text}")

            result = res.json()['choices'][0]['message']['content']
            return self.safe_parse(result, current_order)

        except Exception as e:
            print(f"🔥 AI Process Error: {str(e)}") # Log ထုတ်ကြည့်ဖို့
            return {
                "reply_text": "Server error ခဏနေပြန်ကြိုးစားပါခင်ဗျာ",
                "intent": "info_gathering",
                "final_order_data": current_order # Error ဖြစ်ရင်တောင် memory သိမ်းထားတယ်
            }

ai = AI()
