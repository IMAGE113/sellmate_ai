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
            # Context-aware fallback logic
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

        # Item Extraction & Duplicate Merge
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

        # Hallucination Guard for items
        if ai_data.get("items") and not cleaned_items:
            return {
                "reply_text": "မီနူးထဲမှာ မရှိတဲ့ပစ္စည်း ဖြစ်နေပါတယ်ခင်ဗျာ။ တစ်ချက်ပြန်စစ်ပေးပါ။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

        # Payment & Data Merge
        payment = (ai_data.get("payment_method") or current_order.get("payment_method", "COD")).lower()
        payment = "Prepaid" if "pre" in payment else "COD"

        merged = {
            "customer_name": str(ai_data.get("customer_name") or current_order.get("customer_name", "")),
            "phone_no": str(ai_data.get("phone_no") or current_order.get("phone_no", "")),
            "address": str(ai_data.get("address") or current_order.get("address", "")),
            "payment_method": payment,
            "items": cleaned_items
        }

        # 🔥 Fix 1: Reply Sanitation (Prevents Telegram Crash)
        reply = str(data.get("reply_text") or "ဘာများ မှာယူမလဲခင်ဗျာ?").strip()
        
        return {
            "reply_text": reply,
            "intent": data.get("intent", "info_gathering"),
            "final_order_data": merged
        }

    def prompt(self, shop, menu, current_order):
    return f"""
You are a PROFESSIONAL AI WAITER for {shop}. Your ONLY goal is to complete the order.
Output ONLY JSON. 

━━━━━━━━━━━━━━━━━━━━━━
🚨 CRITICAL RULES (STRICT ENFORCEMENT)
━━━━━━━━━━━━━━━━━━━━━━
1. DO NOT LOOP: If you already have the Customer Name, Phone, Address, and Items, STOP ASKING QUESTIONS.
2. SUMMARY FIRST: Once you have all data, provide a CLEAR Summary and ask the user: "အော်ဒါတင်ဖို့ အတည်ပြုပေးပါ (Confirm လို့ ရိုက်ပေးပါ)။"
3. NO SMALL TALK: Don't wish them health or long life constantly. Be professional and efficient.
4. LANGUAGE: Always respond in clear Myanmar Unicode.
5. DATA PERSISTENCE: Use the CURRENT STATE provided. If a field is filled, don't ask for it again.

━━━━━━━━━━━━━━━━━━━━━━
📌 CONTEXT DATA
━━━━━━━━━━━━━━━━━━━━━━
MENU: {json.dumps(menu, ensure_ascii=False)}
CURRENT STATE: {json.dumps(current_order, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━
🎯 OUTPUT GUIDELINE
━━━━━━━━━━━━━━━━━━━━━━
- If info is missing: reply_text = "ကျန်ရှိနေတဲ့ [Name/Phone/Address] လေး ပြောပေးပါဦးခင်ဗျာ။"
- If all info is present: 
    reply_text = "အော်ဒါ အနှစ်ချုပ်ကတော့... [Items & Total]. အားလုံးမှန်ကန်ရင် Confirm လို့ ရိုက်ပြီး အော်ဒါတင်နိုင်ပါပြီ။"
    intent = "info_gathering" (Wait for user to say Confirm)

OUTPUT JSON ONLY:
{{
  "reply_text": "...",
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
        prompt_text = self.prompt(shop, menu, current_order)
        
        # 🔥 Fix 2: Input Normalization (Edge-case Confirm Bug)
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

            # Strict Confirm Guard
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
