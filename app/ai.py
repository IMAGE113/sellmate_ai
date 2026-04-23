import os, json, httpx, re, asyncio

http_client = httpx.AsyncClient(timeout=20.0)

class AI:
    # ✅ HELPERS FOR DATA INTEGRITY
    def pick(self, new, old):
        """AI က အသစ်ပေးတာရှိမှ ယူမယ်၊ မဟုတ်ရင် အဟောင်းကိုပဲ ဆက်ကိုင်ထားမယ်"""
        if isinstance(new, str) and new.strip():
            return new.strip()
        if isinstance(new, (int, float)):
            return new
        return old

    # ==========================================
    # 🔥 BACKEND SUMMARY BUILDER
    # ==========================================
    def build_summary_layout(self, order):
        item_lines = "\n".join([f"• {item['name']} x {item['qty']}" for item in order['items']])
        return f"""📝 **အော်ဒါအနှစ်ချုပ်**
━━━━━━━━━━━━━━
🛒 **မှာယူသည့်ပစ္စည်းများ:**
{item_lines}

👤 **အမည်:** {order['customer_name']}
📞 **ဖုန်း:** {order['phone_no']}
📍 **လိပ်စာ:** {order['address']}
💳 **ငွေပေးချေမှု:** {order['payment_method']}
━━━━━━━━━━━━━━
မှန်ကန်ပါက **Confirm** ဟု ရိုက်ပေးပါ။"""

    # ==========================================
    # 🔥 SAFE_PARSE (FINAL PRODUCTION HARDENING)
    # ==========================================
    def safe_parse(self, text, current_order, menu):
        try:
            match = re.search(r'\{.*?\}', text, re.DOTALL)
            json_text = match.group() if match else text
            data = json.loads(json_text)
        except Exception:
            return {
                "reply_text": "အော်ဒါတင်ပေးဖို့အတွက် အမည်၊ ဖုန်းနံပါတ်၊ လိပ်စာလေး ပေးပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

        ai_data = data.get("final_order_data", {})
        menu_map = {m["name"].lower(): m["name"] for m in menu}

        # 🛒 ITEM MERGING (FIXED FOR DUPLICATION)
        raw_items = ai_data.get("items")
        merged_items = {item["name"]: item["qty"] for item in current_order.get("items", [])}

        if raw_items:
            for item in raw_items:
                name_raw = str(item.get("name", "")).strip().lower()
                qty = max(1, int(item.get("qty", 1)))
                original_name = next((m["name"] for m in menu if m["name"].lower() == name_raw), None)
                if original_name:
                    merged_items[original_name] = qty # Update qty if exists, else add

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        # 💳 PAYMENT LOGIC (FIXED FOR COD/PREPAID DETECTION)
        # AI ဆီက လာတဲ့ message text ထဲမှာ ပါသလားအရင်စစ်မယ် (AI JSON က အမြဲမမှန်လို့)
        input_text = text.upper()
        payment = current_order.get("payment_method", "")
        
        if any(x in input_text for x in ["COD", "CASH", "အိမ်ရောက်", "လက်ငင်း"]):
            payment = "COD (အိမ်ရောက်ငွေချေ)"
        elif any(x in input_text for x in ["PRE", "KPAY", "WAVE", "လွှဲ"]):
            payment = "Prepaid"
        elif ai_data.get("payment_method"):
            p_raw = str(ai_data["payment_method"]).upper()
            if "COD" in p_raw or "CASH" in p_raw: payment = "COD (အိမ်ရောက်ငွေချေ)"
            elif "PRE" in p_raw or "PAY" in p_raw: payment = "Prepaid"

        # 👤 DATA MERGE
        merged = {
            "customer_name": self.pick(ai_data.get("customer_name"), current_order.get("customer_name", "")),
            "phone_no": self.pick(ai_data.get("phone_no"), current_order.get("phone_no", "")),
            "address": self.pick(ai_data.get("address"), current_order.get("address", "")),
            "payment_method": payment,
            "items": cleaned_items
        }

        # ✅ Check if all fields are filled
        all_info_present = all([
            merged["customer_name"], 
            merged["phone_no"], 
            merged["address"], 
            merged["payment_method"], 
            len(merged["items"]) > 0
        ])
        
        if all_info_present:
            return {"reply_text": self.build_summary_layout(merged), "intent": "confirm_order", "final_order_data": merged}
        
        return {
            "reply_text": str(data.get("reply_text") or "ဆက်လက်မှာယူနိုင်ပါတယ်ခင်ဗျာ။").strip(),
            "intent": "info_gathering",
            "final_order_data": merged
        }

    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. Respond in UNICODE BURMESE.
Task: Extract order details (Name, Phone, Address, Payment Method, Items).

🚨 RULES:
1. If user doesn't mention payment, ask: "COD (အိမ်ရောက်ငွေချေ) လား ဒါမှမဟုတ် Prepaid (ငွေကြိုလွှဲ) လားခင်ဗျာ?"
2. Return JSON only. 'final_order_data' MUST contain all current and new fields.

CONTEXT: {json.dumps(current_order, ensure_ascii=False)}
MENU: {json.dumps(menu, ensure_ascii=False)}
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", clean_text)
        
        # 🔄 RESTART LOGIC
        if any(w in clean_input for w in ["restart", "cancel", "ပြန်လုပ်", "အစကနေ"]) or clean_text == "/start":
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "intent": "info_gathering",
                "final_order_data": {"customer_name": "", "phone_no": "", "address": "", "payment_method": "", "items": []}
            }

        for attempt in range(2):
            try:
                res = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": "Return JSON only. Unicode Burmese only."},
                            {"role": "user", "content": f"{self.prompt(shop, menu, current_order)}\n\nUSER: {text}"}
                        ],
                        "temperature": 0,
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code != 200: raise Exception(res.text)
                
                content = res.json()["choices"][0]["message"]["content"]
                result = self.safe_parse(text, current_order, menu) # Pass original text for better detection

                # ✅ CONFIRM GUARD
                confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်ပါတယ်", "အိုကေ", "မှာမယ်"]
                is_confirm = any(w in clean_input for w in confirm_words)
                if result["intent"] == "confirm_order" and not is_confirm:
                    result["intent"] = "info_gathering"

                return result
            except Exception:
                if attempt == 1:
                    return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဦးခင်ဗျာ။", "intent": "info_gathering", "final_order_data": current_order}
                await asyncio.sleep(1)

ai = AI()
