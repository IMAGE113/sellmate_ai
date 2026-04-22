import os, json, httpx, re

http_client = httpx.AsyncClient(timeout=20.0)

class AI:
    # ==========================================
    # 🔥 SAFE_PARSE (FINAL PRODUCTION HARDENING)
    # ==========================================
    def safe_parse(self, text, current_order, menu):
        try:
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
        except Exception:
            # Error တက်ရင် လိုအပ်တဲ့ အချက်အလက်ကို တစ်ကြောင်းတည်း တိုတိုပဲ ပြန်မေးမယ်
            return {
                "reply_text": "အော်ဒါတင်ပေးဖို့အတွက် အမည်၊ ဖုန်းနံပါတ်၊ လိပ်စာ အပြည့်အစုံလေး ရေးပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

        ai_data = data.get("final_order_data", {})

        raw_items = ai_data.get("items") or current_order.get("items", [])
        merged_items = {}
        for item in raw_items:
            name = str(item.get("name", "")).strip()
            try:
                qty = max(1, int(item.get("qty", 1)))
            except:
                qty = 1

            original_name = next((m["name"] for m in menu if m["name"].lower() == name.lower()), None)
            if not original_name: continue

            merged_items[original_name] = merged_items.get(original_name, 0) + qty

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        # Payment Logic Refinement
        payment = (ai_data.get("payment_method") or current_order.get("payment_method", "COD")).lower()
        if "pre" in payment or "kpay" in payment or "wave" in payment:
            payment = "Prepaid"
        else:
            payment = "COD"

        merged = {
            "customer_name": str(ai_data.get("customer_name") or current_order.get("customer_name", "")),
            "phone_no": str(ai_data.get("phone_no") or current_order.get("phone_no", "")),
            "address": str(ai_data.get("address") or current_order.get("address", "")),
            "payment_method": payment,
            "items": cleaned_items
        }

        reply = str(data.get("reply_text") or "ဆက်လက်မှာယူနိုင်ပါတယ်ခင်ဗျာ။").strip()
        
        return {
            "reply_text": reply,
            "intent": data.get("intent", "info_gathering"),
            "final_order_data": merged
        }

    # ==========================================
    # 🎯 IMPROVED PROMPT (DIRECT & CLEAN SUMMARY)
    # ==========================================
    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. 
Task: Extract order details (Items, Name, Phone, Address).

━━━━━━━━━━━━━━━━━━━━━━
🚨 CRITICAL RULES (STRICT)
━━━━━━━━━━━━━━━━━━━━━━
1. BE DIRECT: No extra greetings or repeating customer names (e.g., No "Mingalabar Htet Aung").
2. TOKEN SAVING: If info is missing, ask for Name, Phone, and Address together in ONE short sentence.
3. LOGIC: ONLY ask for personal info after at least ONE item is added to the cart.
4. ORDER SUMMARY: Show the summary ONLY when all info is collected.

━━━━━━━━━━━━━━━━━━━━━━
📋 ORDER SUMMARY LAYOUT
━━━━━━━━━━━━━━━━━━━━━━
📝 **အော်ဒါအနှစ်ချုပ်**
━━━━━━━━━━━━━━
🛒 **မှာယူသည့်ပစ္စည်းများ:**
• [Item Name] x [Qty]

👤 **အမည်:** [Name]
📞 **ဖုန်း:** [Phone]
📍 **လိပ်စာ:** [Address]
💳 **ငွေပေးချေမှု:** [COD or Prepaid]
━━━━━━━━━━━━━━
မှန်ကန်ပါက **Confirm** ဟု ရိုက်ပေးပါ။

━━━━━━━━━━━━━━━━━━━━━━
📌 CONTEXT DATA
━━━━━━━━━━━━━━━━━━━━━━
MENU: {json.dumps(menu, ensure_ascii=False)}
CURRENT STATE: {json.dumps(current_order, ensure_ascii=False)}

OUTPUT JSON ONLY:
{{
  "reply_text": "Short Burmese sentence",
  "intent": "info_gathering OR confirm_order",
  "final_order_data": {{ ... }}
}}
"""

    async def process(self, text, shop, menu, current_order):
        # 🔥 Fix: Reset data when /start is called to prevent old data persistence
        if text.strip() == "/start":
            blank_order = {"customer_name": "", "phone_no": "", "address": "", "payment_method": "COD", "items": []}
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "intent": "info_gathering",
                "final_order_data": blank_order
            }

        prompt_text = self.prompt(shop, menu, current_order)
        clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", text.lower())

        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Return JSON. No conversational filler."},
                        {"role": "user", "content": f"{prompt_text}\n\nUSER: {text}"}
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"}
                }
            )

            if res.status_code != 200: raise Exception(res.text)
            content = res.json()["choices"][0]["message"]["content"]
            result = self.safe_parse(content, current_order, menu)

            confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်ပါတယ်", "အိုကေ", "မှာမယ်"]
            if result["intent"] == "confirm_order":
                if clean_input not in confirm_words and not any(w in clean_input for w in confirm_words):
                    result["intent"] = "info_gathering"
                
                if not result["final_order_data"].get("items"):
                    result["intent"] = "info_gathering"

            return result

        except Exception as e:
            print("🔥 AI ERROR:", str(e))
            return {"reply_text": "နားမလည်လိုက်လို့ တစ်ချက်ပြန်ပြောပေးပါဦးခင်ဗျာ။", "intent": "info_gathering", "final_order_data": current_order}

ai = AI()
