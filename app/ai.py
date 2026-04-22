import os, json, httpx, re

http_client = httpx.AsyncClient(timeout=20.0)


class AI:
    # =========================
    # CLEAN JSON PARSER
    # =========================
    def safe_parse(self, text, current_order):
        try:
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)

        except Exception:
            return {
                "reply_text": "နားမလည်ပါဘူးခင်ဗျာ။ တစ်ချက်ပြန်ပြောပေးပါဦး။",
                "intent": "info_gathering",
                "final_order_data": current_order
            }

        ai = data.get("final_order_data", {})

        # 🔥 SAFE MERGE (NO DATA LOSS EVER)
        merged = {
            "customer_name": ai.get("customer_name") or current_order.get("customer_name", ""),
            "phone_no": ai.get("phone_no") or current_order.get("phone_no", ""),
            "address": ai.get("address") or current_order.get("address", ""),
            "payment_method": ai.get("payment_method") or current_order.get("payment_method", "COD"),
            "items": ai.get("items") if ai.get("items") else current_order.get("items", [])
        }

        return {
            "reply_text": data.get("reply_text") or "ဘာများ မှာယူမလဲခင်ဗျာ?",
            "intent": data.get("intent", "info_gathering"),
            "final_order_data": merged
        }

    # =========================
    # ULTRA STABLE PROMPT (FIXED)
    # =========================
    def prompt(self, shop, menu, current_order):
        return f"""
You are a PROFESSIONAL AI ORDER WAITER for: {shop}

━━━━━━━━━━━━━━━━━━━━━━
🎯 STRICT RULES (MANDATORY)
━━━━━━━━━━━━━━━━━━━━━━
1. LANGUAGE: Always reply in pure Myanmar Unicode (Pyidaungsu font style).
2. FONT FIX: Do not use mixed characters. Ensure sentences are natural and meaningful.
3. PRODUCT NAMES: Use the exact names from the MENU. Do not translate them to Myanmar (e.g., if menu is 'Latte', use 'Latte').
4. JSON ONLY: Your entire response must be a single valid JSON object. No extra text before or after.
5. NO HALLUCINATION: If an item is not in the menu, refuse politely.

━━━━━━━━━━━━━━━━━━━━━━
📌 MENU DATA
━━━━━━━━━━━━━━━━━━━━━━
{json.dumps(menu, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━
📌 CURRENT ORDER STATE
━━━━━━━━━━━━━━━━━━━━━━
{json.dumps(current_order, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━
🧠 LOGIC STEPS
━━━━━━━━━━━━━━━━━━━━━━
1. Check the USER's input.
2. Update the 'final_order_data' by merging USER info into the CURRENT ORDER STATE.
3. Determine the 'intent':
   - "info_gathering": If info is still missing (items, qty, name, phone, or address).
   - "confirm_order": ONLY if ALL info (Items, Name, Phone, Address, Payment) is present and correct.
4. Craft 'reply_text': Ask for the next missing info naturally in Myanmar Unicode.

━━━━━━━━━━━━━━━━━━━━━━
📤 OUTPUT FORMAT (STRICT JSON)
━━━━━━━━━━━━━━━━━━━━━━
Return exactly this structure:
{{
  "reply_text": "မြန်မာစာသီးသန့် (Unicode)",
  "intent": "info_gathering",
  "final_order_data": {{
    "customer_name": "string",
    "phone_no": "string",
    "address": "string",
    "payment_method": "COD",
    "items": [
      {{ "name": "exact_menu_name", "qty": 1 }}
    ]
  }}
}}
"""

    # =========================
    # MAIN PROCESS
    # =========================
    async def process(self, text, shop, menu, current_order):

        prompt = self.prompt(shop, menu, current_order)

        try:
            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an order bot. Output STRICT JSON only. No markdown."
                        },
                        {
                            "role": "user",
                            "content": prompt + f"\n\nUSER: {text}"
                        }
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"}
                }
            )

            if res.status_code != 200:
                raise Exception(res.text)

            content = res.json()["choices"][0]["message"]["content"]
            return self.safe_parse(content, current_order)

        except Exception as e:
            print("🔥 AI ERROR:", str(e))

            return {
                "reply_text": "Server error ခဏနေပြန်ကြိုးစားပါခင်ဗျာ",
                "intent": "info_gathering",
                "final_order_data": current_order
            }


ai = AI()
