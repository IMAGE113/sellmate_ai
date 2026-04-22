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
            if current_order.get("items"):
                return {
                    "reply_text": "အော်ဒါဆက်လုပ်ချင်ပါသေးလားခင်ဗျာ? ဆက်ပြောနိုင်ပါတယ်။",
                    "intent": "info_gathering",
                    "final_order_data": current_order
                }
            return {
                "reply_text": "ဘာများ မှာယူမလဲခင်ဗျာ?",
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

        if ai_data.get("items") and not cleaned_items:
            return {
                "reply_text": "မီနူးထဲမှာ မရှိတဲ့ပစ္စည်း ဖြစ်နေပါတယ်ခင်ဗျာ။ တစ်ချက်ပြန်စစ်ပေးပါ။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

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

        reply = str(data.get("reply_text") or "ဘာများ မှာယူမလဲခင်ဗျာ?").strip()
        
        return {
            "reply_text": reply,
            "intent": data.get("intent", "info_gathering"),
            "final_order_data": merged
        }

    # ==========================================
    # 🎯 IMPROVED PROMPT (WITH PAYMENT LOGIC)
    # ==========================================
    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. Your ONLY goal is to complete the order efficiently.
Output ONLY JSON. 

━━━━━━━━━━━━━━━━━━━━━━
🚨 ORDER FLOW PRIORITY
━━━━━━━━━━━━━━━━━━━━━━
1. FIRST STEP: Always prioritize adding ITEMS.
2. ONCE ITEMS EXIST: Ask for missing details one by one: 
   Items -> Name -> Phone -> Address -> Payment Method (COD or Prepaid).
3. DO NOT LOOP: If information exists in CURRENT STATE, do not ask for it again.

━━━━━━━━━━━━━━━━━━━━━━
📋 ORDER SUMMARY DESIGN
━━━━━━━━━━━━━━━━━━━━━━
When showing the summary, use this format:
---
🛍️ **Order Summary**
• [Item Name] x [Qty]
------------------
💰 **Total: [Amount] Kyats**
👤 **Customer:** [Name]
📞 **Phone:** [Phone]
📍 **Address:** [Address]
💳 **Payment:** [COD or Prepaid]
---
မှန်ကန်ပါက **Confirm** ဟု ရိုက်ပေးပါ။

━━━━━━━━━━━━━━━━━━━━━━
📌 CONTEXT DATA
━━━━━━━━━━━━━━━━━━━━━━
MENU: {json.dumps(menu, ensure_ascii=False)}
CURRENT STATE: {json.dumps(current_order, ensure_ascii=False)}

OUTPUT JSON ONLY:
{{
  "reply_text": "Myanmar response following the flow above",
  "intent": "info_gathering OR confirm_order",
  "final_order_data": {{ 
    "customer_name": "", 
    "phone_no": "", 
    "address": "", 
    "payment_method": "COD", 
    "items": [] 
  }}
}}
"""

    async def process(self, text, shop, menu, current_order):
        if text.strip() == "/start":
            return {
                "reply_text": f"မင်္ဂလာပါခင်ဗျာ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ? မှာယူလိုတဲ့ ပစ္စည်းအမည်လေး ပြောပေးပါ။",
                "intent": "info_gathering",
                "final_order_data": current_order
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
                        {"role": "system", "content": "Output STRICT JSON only."},
                        {"role": "user", "content": prompt_text + f"\n\nUSER: {text}"}
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
            return {"reply_text": f"{shop} မှာ ဘာများ မှာယူမလဲခင်ဗျာ?", "intent": "info_gathering", "final_order_data": current_order}

ai = AI()
