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
    # ULTRA STABLE PROMPT
    # =========================
    def prompt(self, shop, menu, current_order):

        return f"""
You are a PROFESSIONAL AI ORDER WAITER for a restaurant: {shop}

YOU MUST FOLLOW THESE RULES STRICTLY:

━━━━━━━━━━━━━━━━━━━━━━
❌ FORBIDDEN
━━━━━━━━━━━━━━━━━━━━━━
- Do NOT create items not in menu
- Do NOT output extra text
- Do NOT explain system
- ONLY JSON output

━━━━━━━━━━━━━━━━━━━━━━
📌 MENU (ONLY VALID ITEMS)
━━━━━━━━━━━━━━━━━━━━━━
{json.dumps(menu, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━
📌 CURRENT ORDER STATE (IMPORTANT MEMORY)
━━━━━━━━━━━━━━━━━━━━━━
{json.dumps(current_order, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━
🧠 BEHAVIOR RULES
━━━━━━━━━━━━━━━━━━━━━━
1. Always continue from CURRENT ORDER STATE
2. Never reset previous data
3. Ask only missing info
4. If everything complete → set intent = "confirm_order"
5. If item not in menu → politely refuse in Myanmar

━━━━━━━━━━━━━━━━━━━━━━
🧾 FLOW
━━━━━━━━━━━━━━━━━━━━━━
Items → Qty → Name → Phone → Address → Payment → Confirm

━━━━━━━━━━━━━━━━━━━━━━
📤 OUTPUT FORMAT (STRICT JSON ONLY)
━━━━━━━━━━━━━━━━━━━━━━
Return EXACTLY like this:

{{
  "reply_text": "Myanmar response only",
  "intent": "info_gathering",
  "final_order_data": {{
    "customer_name": "",
    "phone_no": "",
    "address": "",
    "payment_method": "COD",
    "items": [
      {{ "name": "item_name", "qty": 1 }}
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
