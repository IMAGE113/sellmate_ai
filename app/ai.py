import os, json, httpx, re, asyncio

http_client = httpx.AsyncClient(timeout=20.0)

class AI:
    # ✅ HELPERS FOR DATA INTEGRITY
    def pick(self, new, old):
        """AI က အသစ်ပေးတာရှိမှ ယူမယ်၊ မဟုတ်ရင် အဟောင်းကိုပဲ ဆက်ကိုင်ထားမယ်"""
        # String ဖြစ်ပြီး အထဲမှာ စာပါမှ ယူမယ်
        if isinstance(new, str) and new.strip():
            return new.strip()
        # Number ဖြစ်ရင်လည်း ယူမယ် (qty အတွက်)
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

        # 🛒 ITEM MERGING
        raw_items = ai_data.get("items")
        merged_items = {}
        # အရင်ရှိနေတဲ့ items တွေကို base အနေနဲ့ ထည့်ထားမယ်
        for item in current_order.get("items", []):
            merged_items[item["name"]] = item["qty"]

        if raw_items:
            # AI ဆီက data အသစ်လာရင် merge လုပ်မယ်
            for item in raw_items:
                name = str(item.get("name", "")).strip().lower()
                qty = max(1, int(item.get("qty", 1)))
                if name in menu_map:
                    original_name = menu_map[name]
                    merged_items[original_name] = qty # Overwrite or Add qty

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        # 💳 PAYMENT LOGIC
        payment_raw = str(ai_data.get("payment_method") or "").upper()
        if any(x in payment_raw for x in ["PRE", "KPAY", "WAVE"]):
            payment = "Prepaid"
        elif any(x in payment_raw for x in ["COD", "CASH", "အိမ်ရောက်"]):
            payment = "COD (အိမ်ရောက်ငွေချေ)"
        else:
            payment = current_order.get("payment_method", "")

        # 👤 DATA MERGE (အဟောင်းနဲ့ အသစ်ကို သေချာ ပေါင်းစပ်မယ်)
        merged = {
            "customer_name": self.pick(ai_data.get("customer_name"), current_order.get("customer_name", "")),
            "phone_no": self.pick(ai_data.get("phone_no"), current_order.get("phone_no", "")),
            "address": self.pick(ai_data.get("address"), current_order.get("address", "")),
            "payment_method": payment,
            "items": cleaned_items
        }

        # Check if all fields are filled
        # items က list ဖြစ်လို့ len() နဲ့ စစ်တာ ပိုသေချာပါတယ်
        all_info_present = all([
            merged["customer_name"], 
            merged["phone_no"], 
            merged["address"], 
            merged["payment_method"], 
            len(merged["items"]) > 0
        ])
        
        if all_info_present:
            # Edit detection
            if current_order.get("items") and cleaned_items != current_order.get("items"):
                reply = "အော်ဒါကို ပြင်ဆင်ပြီးပါပြီ။\n\n" + self.build_summary_layout(merged)
            else:
                reply = self.build_summary_layout(merged)
            
            return {"reply_text": reply, "intent": "confirm_order", "final_order_data": merged}
        
        return {
            "reply_text": str(data.get("reply_text") or "ဆက်လက်မှာယူနိုင်ပါတယ်ခင်ဗျာ။").strip(),
            "intent": "info_gathering",
            "final_order_data": merged
        }

    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. Respond in UNICODE BURMESE.
Task: Extract order details accurately.

🚨 RULES:
1. Extract Name, Phone, Address, Payment, and Items.
2. IMPORTANT: Your JSON 'final_order_data' MUST include all fields from CURRENT STATE plus any new updates. DO NOT return empty strings for fields you already have in CURRENT STATE.
3. If info is missing, ask briefly.

CONTEXT (CURRENT STATE): {json.dumps(current_order, ensure_ascii=False)}
MENU: {json.dumps(menu, ensure_ascii=False)}

OUTPUT JSON ONLY.
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", clean_text)
        
        # 🔄 RESTART LOGIC
        restart_words = ["ပြန်လုပ်", "restart", "cancel", "မလိုတော့", "အသစ်", "အစကနေ"]
        if any(w in clean_input for w in restart_words) or clean_text == "/start":
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
                            {"role": "system", "content": "Return JSON only. Unicode Burmese only. Be concise."},
                            {"role": "user", "content": f"{self.prompt(shop, menu, current_order)}\n\nUSER: {text}"}
                        ],
                        "temperature": 0,
                        "response_format": {"type": "json_object"}
                    }
                )

                if res.status_code != 200: raise Exception(res.text)
                
                content = res.json()["choices"][0]["message"]["content"]
                result = self.safe_parse(content, current_order, menu)

                # ✅ SMART CONFIRM GUARD
                confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်ပါတယ်", "အိုကေ", "မှာမယ်", "အတည်ပြု"]
                negative_words = ["မဟုတ်", "မှား", "ပြင်", "change", "wrong", "မမှန်"]
                
                is_confirm = any(w in clean_input for w in confirm_words)
                has_negative = any(w in clean_input for w in negative_words)

                if result["intent"] == "confirm_order":
                    # အချက်အလက်စုံပေမယ့် user က confirm မပြောသေးရင် intent ကို info_gathering မှာပဲ ထားမယ်
                    if not is_confirm or has_negative:
                        result["intent"] = "info_gathering"

                return result

            except Exception as e:
                if attempt == 1:
                    return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဦးခင်ဗျာ။", "intent": "info_gathering", "final_order_data": current_order}
                await asyncio.sleep(1)

ai = AI()
