import os, json, httpx, re, asyncio

http_client = httpx.AsyncClient(timeout=20.0)

class AI:
    # ✅ HELPERS
    def pick(self, new, old):
        """AI ဆီက data အသစ်ပါမှ ယူမယ်၊ မဟုတ်ရင် အဟောင်းကို ဆက်ကိုင်ထားမယ်"""
        if isinstance(new, str) and new.strip():
            return new.strip()
        if isinstance(new, (int, float)):
            return new
        return old

    def build_summary_layout(self, order):
        """Final Summary Layout (Unicode Burmese)"""
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
မှန်ကန်ပါက **Confirm** နှိပ်ပေးပါ။ ပြင်ချင်တာရှိပါကလည်း ပြောနိုင်ပါတယ်ခင်ဗျာ။"""

    # ✅ SAFE_PARSE WITH ADVANCED EDIT LOGIC
    def safe_parse(self, content, current_order, menu, user_input):
        try:
            match = re.search(r'\{.*?\}', content, re.DOTALL)
            json_text = match.group() if match else content
            data = json.loads(json_text)
        except Exception:
            return {
                "reply_text": "နားမလည်လိုက်လို့ ပြန်ပြောပေးပါဦးခင်ဗျာ။", 
                "intent": "info_gathering", 
                "final_order_data": current_order
            }

        ai_data = data.get("final_order_data", {})
        
        # 🛒 SMART ITEM EDIT/REPLACE DETECTION
        # User input ထဲမှာ ပြင်ချင်တဲ့ အရိပ်အယောင်ပါသလား စစ်မယ်
        edit_triggers = ["မဟုတ်", "မယူ", "မသောက်", "ပြင်", "change", "replace", "remove", "အစား", "ဖြုတ်"]
        is_edit_mode = any(word in user_input.lower() for word in edit_triggers)
        
        merged_items = {item["name"]: item["qty"] for item in current_order.get("items", [])}
        raw_items = ai_data.get("items", [])

        if raw_items:
            if is_edit_mode:
                # Edit mode ဆိုရင် AI ပေးတဲ့ ပစ္စည်းအသစ်တွေနဲ့ပဲ အစားထိုးမယ်
                new_list = {}
                for item in raw_items:
                    name_raw = str(item.get("name", "")).strip().lower()
                    original_name = next((m["name"] for m in menu if m["name"].lower() == name_raw), None)
                    if original_name:
                        new_list[original_name] = max(1, int(item.get("qty", 1)))
                if new_list:
                    merged_items = new_list
            else:
                # Normal mode: ရှိပြီးသားထဲကို ပေါင်းမယ် (သို့) Qty update လုပ်မယ်
                for item in raw_items:
                    name_raw = str(item.get("name", "")).strip().lower()
                    original_name = next((m["name"] for m in menu if m["name"].lower() == name_raw), None)
                    if original_name:
                        merged_items[original_name] = max(1, int(item.get("qty", 1)))

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        # 👤 DATA MERGE
        merged = {
            "customer_name": self.pick(ai_data.get("customer_name"), current_order.get("customer_name", "")),
            "phone_no": self.pick(ai_data.get("phone_no"), current_order.get("phone_no", "")),
            "address": self.pick(ai_data.get("address"), current_order.get("address", "")),
            "payment_method": self.pick(ai_data.get("payment_method"), current_order.get("payment_method", "")),
            "items": cleaned_items
        }

        return {"final_order_data": merged, "reply_text": data.get("reply_text")}

    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI WAITER for {shop}. Respond in UNICODE BURMESE.
Extract: Name, Phone, Address, Payment, Items.
If user wants to CHANGE/REPLACE/REMOVE an item, update the 'items' list accordingly.
CONTEXT: {json.dumps(current_order, ensure_ascii=False)}
MENU: {json.dumps(menu, ensure_ascii=False)}
Return JSON with 'reply_text' and 'final_order_data'.
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        clean_input = re.sub(r"[^\w\u1000-\u109F]+", "", clean_text)
        
        # 🔄 RESTART LOGIC
        if any(w in clean_input for w in ["restart", "ပြန်လုပ်", "/start"]):
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "intent": "info_gathering",
                "final_order_data": {"customer_name": "", "phone_no": "", "address": "", "payment_method": "", "items": []},
                "ui": "main_menu"
            }

        # ✅ REVIEW STATE GATEKEEPER (Pre-AI Check)
        is_ready = all([
            current_order.get("customer_name"),
            current_order.get("phone_no"),
            current_order.get("address"),
            current_order.get("payment_method"),
            len(current_order.get("items", [])) > 0
        ])

        if is_ready:
            confirm_words = ["confirm", "yes", "ok", "ဟုတ်", "မှန်တယ်", "အိုကေ", "မှာမယ်", "ရပြီ"]
            edit_words = ["မဟုတ်", "မယူ", "မသောက်", "ပြင်", "change", "replace", "remove", "အစား", "ဖြုတ်"]
            
            is_confirm = any(w in clean_input for w in confirm_words)
            is_edit_intent = any(w in clean_text for w in edit_words)
            mentions_menu = any(m["name"].lower() in clean_text for m in menu)

            # Confirm Case
            if is_confirm and not mentions_menu:
                return {
                    "reply_text": "အော်ဒါကို အတည်ပြုလိုက်ပါပြီ။ ကျေးဇူးတင်ပါတယ်! 🙏",
                    "intent": "confirm_order",
                    "final_order_data": current_order
                }

            # If user is NOT editing and NOT mentioning menu → Keep Summary
            if not is_edit_intent and not mentions_menu:
                return {
                    "reply_text": self.build_summary_layout(current_order),
                    "intent": "review_order",
                    "final_order_data": current_order,
                    "ui": "confirm_buttons"
                }

        # 🧠 AI PARSING ENGINE
        for attempt in range(2):
            try:
                res = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": f"{self.prompt(shop, menu, current_order)}\n\nUSER: {text}"}],
                        "temperature": 0, "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code != 200: raise Exception(res.text)

                content = res.json()["choices"][0]["message"]["content"]
                parse_result = self.safe_parse(content, current_order, menu, text)
                updated_order = parse_result["final_order_data"]

                # Post-AI Readiness Check
                is_now_ready = all([
                    updated_order.get("customer_name"),
                    updated_order.get("phone_no"),
                    updated_order.get("address"),
                    updated_order.get("payment_method"),
                    len(updated_order.get("items", [])) > 0
                ])

                if is_now_ready:
                    return {
                        "reply_text": self.build_summary_layout(updated_order),
                        "intent": "review_order",
                        "final_order_data": updated_order,
                        "ui": "confirm_buttons"
                    }

                # If still gathering info
                return {
                    "reply_text": parse_result["reply_text"],
                    "intent": "info_gathering",
                    "final_order_data": updated_order
                }

            except Exception:
                if attempt == 1:
                    return {"reply_text": "ခဏနေမှ ပြန်ပြောပေးပါဦး။", "intent": "info_gathering", "final_order_data": current_order}
                await asyncio.sleep(1)

ai = AI()
