import os, json, httpx, re

http_client = httpx.AsyncClient(timeout=20.0)

def build_summary(order, menu):
    """Backend-side source of truth for pricing and summary generation."""
    menu_map = {m["name"]: m["price"] for m in menu}
    total = 0
    lines = []

    for item in order["items"]:
        price = menu_map.get(item["name"], 0)
        subtotal = price * item["qty"]
        total += subtotal
        lines.append(f"• {item['name']} x {item['qty']} - {subtotal} MMK")

    return f"""📝 **အော်ဒါအနှစ်ချုပ်**
━━━━━━━━━━━━━━
🛒 **မှာယူသည့်ပစ္စည်းများ:**
{chr(10).join(lines)}

👤 **အမည်:** {order['customer_name']}
📞 **ဖုန်း:** {order['phone_no']}
📍 **လိပ်စာ:** {order['address']}
💳 **ငွေပေးချေမှု:** {order['payment_method']}
💰 **စုစုပေါင်း:** {total} MMK
━━━━━━━━━━━━━━
အချက်အလက်များ မှန်ကန်ပါက **Confirm** ဟု ရိုက်ပေးပါခင်ဗျာ။"""

class AI:
    def safe_parse(self, text, current_order, menu):
        try:
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
        except Exception:
            return {
                "reply_text": "နားမလည်လိုက်လို့ တစ်ချက်ပြန်ပြောပေးပါဦးခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

        ai_data = data.get("final_order_data", {})
        raw_items = ai_data.get("items") or current_order.get("items", [])
        
        # Item merging logic (Backend-side validation)
        merged_items = {}
        for item in raw_items:
            name = str(item.get("name", "")).strip()
            qty = max(1, int(item.get("qty", 1)))
            original_name = next((m["name"] for m in menu if m["name"].lower() == name.lower()), None)
            if original_name:
                merged_items[original_name] = merged_items.get(original_name, 0) + qty

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        # Payment Logic with fallback
        payment_input = str(ai_data.get("payment_method", "")).upper()
        if any(x in payment_input for x in ["PRE", "KPAY", "WAVE", "PAYMENT"]):
            payment = "Prepaid"
        elif any(x in payment_input for x in ["COD", "CASH", "အိမ်ရောက်", "လက်ငင်း"]):
            payment = "COD (အိမ်ရောက်ငွေချေ)"
        else:
            payment = current_order.get("payment_method", "")

        merged = {
            "customer_name": str(ai_data.get("customer_name") or current_order.get("customer_name", "")),
            "phone_no": str(ai_data.get("phone_no") or current_order.get("phone_no", "")),
            "address": str(ai_data.get("address") or current_order.get("address", "")),
            "payment_method": payment,
            "items": cleaned_items
        }

        # 🔥 CTO RULE 1: Backend is the Guard, NOT the decision maker
        intent = data.get("intent", "info_gathering")
        all_info_present = all([merged["customer_name"], merged["phone_no"], merged["address"], merged["payment_method"], merged["items"]])
        
        if intent == "confirm_order" and not all_info_present:
            intent = "info_gathering"

        return {
            "reply_text": str(data.get("reply_text") or ""),
            "intent": intent,
            "final_order_data": merged
        }

    def prompt(self, shop, menu, current_order):
        return f"""
You are a friendly AI Waiter for {shop}. 
Handle the conversation, answer menu questions, and collect order details.

━━━━━━━━━━━━━━━━━━━━━━
🚨 MANDATORY RULES
━━━━━━━━━━━━━━━━━━━━━━
1. MENU FAQ: Use the MENU data below to answer prices or availability.
2. COLLECTION: Gather Name, Phone, Address, and Payment Method (COD/Prepaid) naturally.
3. NO MATH: Never calculate totals or output item prices in the summary.
4. TRIGGER: When all details are ready, set intent to 'confirm_order'.

━━━━━━━━━━━━━━━━━━━━━━
📌 CONTEXT DATA
━━━━━━━━━━━━━━━━━━━━━━
MENU: {json.dumps(menu, ensure_ascii=False)}
CURRENT STATE: {json.dumps(current_order, ensure_ascii=False)}

OUTPUT JSON ONLY:
{{
  "reply_text": "Your natural Burmese response",
  "intent": "info_gathering OR confirm_order",
  "final_order_data": {{ ... }}
}}
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        
        # Greeting/Start handling
        is_greeting = any(greet in clean_text for greet in ["hi", "hello", "ဟိုင်း", "မင်္ဂလာပါ", "/start"])
        if is_greeting and not current_order.get("items"):
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "intent": "info_gathering",
                "final_order_data": {"customer_name": "", "phone_no": "", "address": "", "payment_method": "", "items": []}
            }

        prompt_text = self.prompt(shop, menu, current_order)
        
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Return JSON only."},
                        {"role": "user", "content": f"{prompt_text}\n\nUSER: {text}"}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )

            result = self.safe_parse(res.json()["choices"][0]["message"]["content"], current_order, menu)

            # 🔥 CTO RULE 2 & 3: Confirm logic fix and Backend-generated Summary
            confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်ပါတယ်", "အိုကေ", "မှာမယ်", "အတည်ပြု"]
            clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", clean_text)

            if result["intent"] == "confirm_order":
                # Override AI reply with backend-calculated summary
                result["reply_text"] = build_summary(result["final_order_data"], menu)
                
                # Check if user actually meant to confirm or is just answering a question
                if not any(w in clean_input for w in confirm_words):
                    # If they provided info but didn't say "confirm" yet, keep gathering
                    result["intent"] = "info_gathering"

            return result

        except Exception as e:
            print("🔥 SYSTEM ERROR:", str(e))
            return {"reply_text": "ခဏလေးနော်၊ တစ်ခုခုမှားယွင်းနေလို့ပါ။", "intent": "info_gathering", "final_order_data": current_order}

ai = AI()
