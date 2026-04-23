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
            return {
                "reply_text": "အော်ဒါတင်ပေးဖို့အတွက် အမည်၊ ဖုန်းနံပါတ်၊ လိပ်စာလေး ပေးပေးပါခင်ဗျာ။",
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

        payment = str(ai_data.get("payment_method") or current_order.get("payment_method", "")).upper()
        if any(x in payment for x in ["PRE", "KPAY", "WAVE", "PAYMENT"]):
            payment = "Prepaid"
        elif any(x in payment for x in ["COD", "CASH", "အိမ်ရောက်", "လက်ငင်း"]):
            payment = "COD (အိမ်ရောက်ငွေချေ)"
        else:
            payment = "" 

        merged = {
            "customer_name": str(ai_data.get("customer_name") or current_order.get("customer_name", "")),
            "phone_no": str(ai_data.get("phone_no") or current_order.get("phone_no", "")),
            "address": str(ai_data.get("address") or current_order.get("address", "")),
            "payment_method": payment,
            "items": cleaned_items
        }

        intent = data.get("intent", "info_gathering")
        
        # 🔥 Validation Guard: အချက်အလက်စုံမှသာ Confirm ပေးလုပ်မယ်
        if all([merged["customer_name"], merged["phone_no"], merged["address"], merged["payment_method"], merged["items"]]):
            pass # Keep AI intent if already confirm_order
        else:
            intent = "info_gathering"

        reply = str(data.get("reply_text") or "ဆက်လက်မှာယူနိုင်ပါတယ်ခင်ဗျာ။").strip()
        
        return {
            "reply_text": reply,
            "intent": intent,
            "final_order_data": merged
        }

    # ==========================================
    # 🎯 IMPROVED PROMPT (HARDENED FOR UNICODE & STABILITY)
    # ==========================================
    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. 
Task: Extract order details (Items, Name, Phone, Address, Payment).

━━━━━━━━━━━━━━━━━━━━━━
🚨 MANDATORY RULES (STRICT COMPLIANCE)
━━━━━━━━━━━━━━━━━━━━━━
1. LANGUAGE: Respond in UNICODE BURMESE only. 
2. BE DIRECT: No extra greetings. If user says Hi/Hello, ask what they want to order.
3. CONTEXT: Never ask for information that is already in CURRENT STATE.
4. STEP 1 (Personal Info): Ask for Name, Phone, and Address in ONE sentence if missing.
5. STEP 2 (Payment Inquiry): Once personal info is received, ask for payment method (COD or Prepaid).
6. AUTOMATIC SUMMARY: Once you have Items, Name, Phone, Address, AND Payment, show the summary and set intent to 'confirm_order'.

━━━━━━━━━━━━━━━━━━━━━━
📋 ORDER SUMMARY LAYOUT (ONLY when all data is present)
━━━━━━━━━━━━━━━━━━━━━━
📝 **အော်ဒါအနှစ်ချုပ်**
━━━━━━━━━━━━━━
🛒 **မှာယူသည့်ပစ္စည်းများ:**
• [Item Name] x [Qty]

👤 **အမည်:** [Name]
📞 **ဖုန်း:** [Phone]
📍 **လိပ်စာ:** [Address]
💳 **ငွေပေးချေမှု:** [COD (အိမ်ရောက်ငွေချေ) or Prepaid]
━━━━━━━━━━━━━━
မှန်ကန်ပါက **Confirm** ဟု ရိုက်ပေးပါ။

━━━━━━━━━━━━━━━━━━━━━━
📌 CONTEXT DATA
━━━━━━━━━━━━━━━━━━━━━━
MENU: {json.dumps(menu, ensure_ascii=False)}
CURRENT STATE: {json.dumps(current_order, ensure_ascii=False)}

OUTPUT JSON ONLY:
{{
  "reply_text": "Direct response in Burmese",
  "intent": "info_gathering OR confirm_order",
  "final_order_data": {{ ... }}
}}
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        
        if clean_text == "/start" or any(x == clean_text for x in ["hi", "hello", "ဟိုင်း", "မင်္ဂလာပါ"]):
            blank_order = {"customer_name": "", "phone_no": "", "address": "", "payment_method": "", "items": []}
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "intent": "info_gathering",
                "final_order_data": blank_order
            }

        prompt_text = self.prompt(shop, menu, current_order)
        clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", clean_text)

        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Return JSON. No conversational filler. Burmese only."},
                        {"role": "user", "content": f"{prompt_text}\n\nUSER: {text}"}
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"}
                }
            )

            if res.status_code != 200: raise Exception(res.text)
            content = res.json()["choices"][0]["message"]["content"]
            result = self.safe_parse(content, current_order, menu)

            confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်ပါတယ်", "အိုကေ", "မှာမယ်", "အတည်ပြု"]
            
            # 🔥 Confirm logic check
            if result["intent"] == "confirm_order":
                if not any(w in clean_input for w in confirm_words):
                    # Summary ပြထားပြီးသားဖြစ်ပေမယ့် user က confirm မလုပ်သေးရင် Gathering အဖြစ်ပဲထားမယ်
                    result["intent"] = "info_gathering"

            return result

        except Exception as e:
            print("🔥 AI ERROR:", str(e))
            return {"reply_text": "နားမလည်လိုက်လို့ တစ်ချက်ပြန်ပြောပေးပါဦးခင်ဗျာ။", "intent": "info_gathering", "final_order_data": current_order}

ai = AI()
