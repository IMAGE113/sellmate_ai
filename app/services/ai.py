import os, json, httpx, re, asyncio

http_client = httpx.AsyncClient(timeout=20.0)

class AI:
    def pick(self, new, old):
        if isinstance(new, str) and new.strip():
            return new.strip()
        if isinstance(new, (int, float)):
            return new
        return old

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
မှန်ကန်ပါက **Confirm** နှိပ်ပေးပါ။ ပြင်ချင်တာရှိပါကလည်း ပြောနိုင်ပါတယ်ခင်ဗျာ။ 🙏"""

    def safe_parse(self, content, current_order, menu, user_input):
        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            json_text = match.group() if match else content
            data = json.loads(json_text)
        except Exception:
            return current_order

        ai_data = data.get("final_order_data", {})
        
        # 🛒 SMART ITEM EDIT/REPLACE LOGIC
        edit_triggers = ["မဟုတ်", "မယူ", "မသောက်", "ပြင်", "change", "replace", "remove", "အစား", "ဖြုတ်"]
        is_edit_mode = any(word in user_input.lower() for word in edit_triggers)
        
        merged_items = {item["name"]: item["qty"] for item in current_order.get("items", [])}
        raw_items = ai_data.get("items", [])

        if raw_items:
            if is_edit_mode:
                new_list = {}
                for item in raw_items:
                    name_raw = str(item.get("name", "")).strip().lower()
                    original_name = next((m["name"] for m in menu if m["name"].lower() == name_raw), None)
                    if original_name:
                        new_list[original_name] = max(1, int(item.get("qty", 1)))
                if new_list:
                    merged_items = new_list
            else:
                for item in raw_items:
                    name_raw = str(item.get("name", "")).strip().lower()
                    original_name = next((m["name"] for m in menu if m["name"].lower() == name_raw), None)
                    if original_name:
                        merged_items[original_name] = max(1, int(item.get("qty", 1)))

        cleaned_items = [{"name": k, "qty": v} for k, v in merged_items.items()]

        return {
            "customer_name": self.pick(ai_data.get("customer_name"), current_order.get("customer_name", "")),
            "phone_no": self.pick(ai_data.get("phone_no"), current_order.get("phone_no", "")),
            "address": self.pick(ai_data.get("address"), current_order.get("address", "")),
            "payment_method": self.pick(ai_data.get("payment_method"), current_order.get("payment_method", "")),
            "items": cleaned_items
        }

    def prompt(self, shop, menu, current_order):
        menu_names = [m["name"] for m in menu]
        return f"""
Analyze user input for {shop}. Extract details into JSON.
STRICT RULES:
1. DO NOT translate or change any PRODUCT NAMES from the menu.
2. Use the EXACT spelling from this list: {json.dumps(menu_names)}
3. DO NOT translate the Shop Name.
4. Extract customer_name, phone_no, address, and payment_method.
5. If the user mentions items in Burmese, map them to the corresponding English menu names.

CONTEXT: {json.dumps(current_order, ensure_ascii=False)}
MENU: {json.dumps(menu, ensure_ascii=False)}

Return ONLY JSON with key 'final_order_data'.
"""

    async def process(self, text, shop, menu, current_order):
        clean_text = text.strip().lower()
        
        # 1️⃣ STEP: RESTART & GREETING
        greetings = ["hi", "hello", "hey", "မင်္ဂလာပါ", "start", "/start", "restart"]
        if any(clean_text == g for g in greetings):
            return {
                "reply_text": f"မင်္ဂလာပါ! {shop} မှ ကြိုဆိုပါတယ်။ 🙏\nဒီနေ့ ဘာများ မှာယူမလဲခင်ဗျာ?",
                "final_order_data": {"customer_name": "", "phone_no": "", "address": "", "payment_method": "", "items": []}
            }

        # 2️⃣ AI DATA EXTRACTION (AI ကို Data ဆွဲထုတ်ခိုင်းမယ်)
        updated_order = current_order
        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": f"{self.prompt(shop, menu, current_order)}\n\nUSER: {text}"}],
                    "temperature": 0, 
                    "response_format": {"type": "json_object"}
                }
            )
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"]
                updated_order = self.safe_parse(content, current_order, menu, text)
        except Exception:
            pass

        # 3️⃣ STEP: FLOW CONTROL (Backend ကနေ တစ်ဆင့်ချင်း မေးမယ်)

        # မှာချင်တာ မပါသေးရင်
        if not updated_order.get("items"):
            return {
                "reply_text": "ဘာများ မှာယူမလဲခင်ဗျာ? မှာချင်တဲ့ ပစ္စည်းနဲ့ အရေအတွက်လေး ပြောပေးပါ။",
                "final_order_data": updated_order
            }

        # နာမည်၊ ဖုန်း၊ လိပ်စာ တစ်ခုခု လိုနေရင် (တစ်ကြောင်းတည်း မေးမယ်)
        if not all([updated_order.get("customer_name"), updated_order.get("phone_no"), updated_order.get("address")]):
            return {
                "reply_text": "ဟုတ်ကဲ့ပါခင်ဗျာ။ အော်ဒါပို့ပေးဖို့အတွက် 'အမည်၊ ဖုန်းနံပါတ် နဲ့ လိပ်စာ' လေး တစ်ခါတည်း ပြောပေးပါဦးခင်ဗျာ။",
                "final_order_data": updated_order
            }

        # ငွေချေစနစ် မပါသေးရင်
        if not updated_order.get("payment_method"):
            return {
                "reply_text": "ငွေပေးချေမှုကို 'COD (ပစ္စည်းရောက်ငွေချေ)' လား 'Prepaid (ကြိုတင်ငွေလွှဲ)' လား ဘယ်လိုလုပ်မလဲခင်ဗျာ?",
                "final_order_data": updated_order
            }

        # 4️⃣ STEP: SUMMARY & CONFIRM
        confirm_words = ["confirm", "ok", "ဟုတ်", "မှန်တယ်", "မှာမယ်", "အိုကေ", "yes"]
        clean_input = re.sub(r"[^\w]+", "", clean_text)
        
        if any(w in clean_input for w in confirm_words):
            return {
                "reply_text": "အော်ဒါကို အတည်ပြုလိုက်ပါပြီ။ ကျေးဇူးတင်ပါတယ်! 🙏",
                "intent": "confirmed",
                "final_order_data": updated_order
            }

        return {
            "reply_text": self.build_summary_layout(updated_order),
            "final_order_data": updated_order,
            "ui": "confirm_buttons"
        }

ai = AI()
