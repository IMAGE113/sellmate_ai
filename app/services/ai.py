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
        items = "\n".join([f"• {i['name']} x {i['qty']}" for i in order['items']])
        return f"""📝 **အော်ဒါအနှစ်ချုပ်**
━━━━━━━━━━━━━━
{items}

👤 {order['customer_name']}
📞 {order['phone_no']}
📍 {order['address']}
💳 {order['payment_method']}
━━━━━━━━━━━━━━
Confirm နှိပ်ပါ"""

    def safe_parse(self, content, current_order, menu, user_input):
        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            data = json.loads(match.group() if match else content)
        except:
            return {"reply_text": "နားမလည်ပါဘူး", "final_order_data": current_order}

        ai_data = data.get("final_order_data", {})

        edit_words = ["မဟုတ်","change","replace","remove"]
        is_edit = any(w in user_input.lower() for w in edit_words)

        merged = {i["name"]: i["qty"] for i in current_order.get("items", [])}

        for i in ai_data.get("items", []):
            name = i["name"].lower()
            match_name = next((m["name"] for m in menu if m["name"].lower()==name), None)
            if match_name:
                merged[match_name] = i.get("qty",1)

        items = [{"name":k,"qty":v} for k,v in merged.items()]

        final = {
            "customer_name": self.pick(ai_data.get("customer_name"), current_order.get("customer_name","")),
            "phone_no": self.pick(ai_data.get("phone_no"), current_order.get("phone_no","")),
            "address": self.pick(ai_data.get("address"), current_order.get("address","")),
            "payment_method": self.pick(ai_data.get("payment_method"), current_order.get("payment_method","")),
            "items": items
        }

        return {"final_order_data": final, "reply_text": data.get("reply_text","ok")}

    def prompt(self, shop, menu, current):
        return f"""
AI waiter for {shop}
MENU: {json.dumps(menu)}
CURRENT: {json.dumps(current)}
Return JSON
"""

    async def process(self, text, shop, menu, current):
        for _ in range(2):
            try:
                res = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model":"llama-3.3-70b-versatile",
                        "messages":[{"role":"user","content": self.prompt(shop,menu,current)+"\n"+text}],
                        "response_format":{"type":"json_object"}
                    }
                )
                data = res.json()["choices"][0]["message"]["content"]

                parsed = self.safe_parse(data,current,menu,text)
                order = parsed["final_order_data"]

                ready = all([order.get("customer_name"),order.get("phone_no"),order.get("address"),order.get("items")])

                if ready:
                    return {
                        "reply_text": self.build_summary_layout(order),
                        "final_order_data": order,
                        "ui":"confirm_buttons"
                    }

                return parsed

            except:
                await asyncio.sleep(1)

        return {"reply_text":"error","final_order_data":current}

ai = AI()
