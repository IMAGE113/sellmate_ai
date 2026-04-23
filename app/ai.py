import os, json, httpx, re, asyncio

http_client = httpx.AsyncClient(timeout=20.0)

class AI:
    # ✅ HELPERS FOR DATA INTEGRITY
    def pick(self, new, old):
        if isinstance(new, str) and new.strip():
            return new.strip()
        if isinstance(new, (int, float)):
            return new
        return old

    # ✅ FIX 1: PAYMENT NORMALIZATION (NEW)
    def normalize_payment(self, new, old):
        text = str(new or "").upper()

        if any(x in text for x in ["COD", "CASH", "အိမ်ရောက်", "လက်ငင်း"]):
            return "COD (အိမ်ရောက်ငွေချေ)"
        if any(x in text for x in ["PRE", "KPAY", "WAVE", "လွှဲ"]):
            return "Prepaid"

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
    # 🔥 SAFE_PARSE
    # ==========================================
    def safe_parse(self, content, current_order, menu):
        try:
            match = re.search(r'\{.*?\}', content, re.DOTALL)
            json_text = match.group() if match else content
            data = json.loads(json_text)
        except Exception:
            return {
                "reply_text": "အော်ဒါတင်ပေးဖို့အတွက် အမည်၊ ဖုန်းနံပါတ်၊ လိပ်စာလေး ပေးပေးပါခင်ဗျာ။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

        ai_data = data.get("final_order_data", {})

        # 🛒 ITEM MERGING
        raw_items = ai_data.get("items")
        merged_items = {item["name"]: item["qty"] for item in current_order.get("items", [])}

        if raw_items:
            for item in raw_items:
                name_raw = str(item.get("name", "")).strip().lower()
                qty = max(1, int(item.get("qty", 1)))
                original_name = next((m["name"] for m in menu if m["name"].lower() == name_raw), None)
                if original_name:
                    merged_items[original_name] = qty

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        # 👤 DATA MERGE + ✅ FIXED PAYMENT
        merged = {
            "customer_name": self.pick(ai_data.get("customer_name"), current_order.get("customer_name", "")),
            "phone_no": self.pick(ai_data.get("phone_no"), current_order.get("phone_no", "")),
            "address": self.pick(ai_data.get("address"), current_order.get("address", "")),
            "payment_method": self.normalize_payment(
                ai_data.get("payment_method"),
                current_order.get("payment_method", "")
            ),
            "items": cleaned_items
        }

        all_info_present = all([
            merged["customer_name"], 
            merged["phone_no"], 
            merged["address"], 
            merged["payment_method"], 
            len(merged["items"]) > 0
        ])
        
        if all_info_present:
            return {
                "reply_text": self.build_summary_layout(merged),
                "intent": "review_order",
                "final_order_data": merged
            }
        
        return {
            "reply_text": str(data.get("reply_text") or "ဆက်လက်မှာယူနိုင်ပါတယ်ခင်ဗျာ။").strip(),
            "intent": "info_gathering",
            "final_order_data": merged
        }

    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. Respond in UNICODE BURMESE.
Task: Extract Name, Phone, Address, Payment Method, and Items.

CONTEXT: {json.dumps(current_order, ensure_ascii=False)}
MENU: {json.dumps(menu, ensure_ascii=False)}
Return JSON only.
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", clean_text)

        # 🔄 RESTART
        if any(w in clean_input for w in ["restart", "cancel", "ပြန်လုပ်", "အစကနေ"]) or clean_text == "/start":
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "intent": "info_gathering",
                "final_order_data": {"customer_name": "", "phone_no": "", "address": "", "payment_method": "", "items": []}
            }

        # ✅ FIX 2: REVIEW STATE FREEZE (NO AI CALL)
        is_ready = all([
            current_order.get("customer_name"),
            current_order.get("phone_no"),
            current_order.get("address"),
            current_order.get("payment_method"),
            current_order.get("items")
        ])

        if is_ready:
            confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်ပါတယ်", "အိုကေ", "မှာမယ်"]

            if any(w in clean_input for w in confirm_words):
                return {
                    "reply_text": "အော်ဒါကို အတည်ပြုလိုက်ပါပြီ။ ကျေးဇူးတင်ပါတယ်! 🙏",
                    "intent": "confirm_order",
                    "final_order_data": current_order
                }

            return {
                "reply_text": self.build_summary_layout(current_order),
                "intent": "review_order",
                "final_order_data": current_order
            }

        # 🧠 AI CALL
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

                if res.status_code != 200:
                    raise Exception(res.text)

                content = res.json()["choices"][0]["message"]["content"]
                return self.safe_parse(content, current_order, menu)

            except Exception:
                if attempt == 1:
                    return {
                        "reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဦးခင်ဗျာ။",
                        "intent": "info_gathering",
                        "final_order_data": current_order
                    }
                await asyncio.sleep(1)

ai = AI()
