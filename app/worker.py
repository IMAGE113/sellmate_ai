import asyncio
import json
import hashlib
import os
import httpx
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    try:
        await http_client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(chat_id), "text": text, "parse_mode": "Markdown"},
        )
    except Exception as e:
        print(f"Telegram Send Error: {e}")

def validate(items, menu):
    valid = []
    total = 0
    menu_dict = {m['name'].strip().lower(): m['price'] for m in menu}
    
    if not items or not isinstance(items, list):
        return valid, total

    for i in items:
        name_raw = i.get('name', '').strip()
        name_lower = name_raw.lower()
        if name_lower in menu_dict:
            qty = max(1, int(i.get('qty', 1)))
            price = menu_dict[name_lower]
            valid.append({"name": name_raw, "qty": qty, "price": price})
            total += qty * price
    return valid, total

async def run_worker():
    pool = await get_db_pool(for_worker=True)
    print("Worker is running and watching for tasks...")

    while True:
        try:
            async with pool.acquire() as conn:
                # 1. Fetch Task
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', attempts = attempts + 1, updated_at = NOW()
                    WHERE id = (SELECT id FROM task_queue WHERE status IN ('pending', 'failed') AND attempts < 5
                    ORDER BY created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if not task:
                    await asyncio.sleep(1)
                    continue

                b_id, chat_id, text = task['business_id'], task['chat_id'], (task['user_text'] or "").strip()
                biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)
                if not biz: 
                    await conn.execute("UPDATE task_queue SET status='failed', last_error='Biz not found' WHERE id=$1", task['id'])
                    continue

                token, shop_name = biz['tg_bot_token'], biz['name']

                try:
                    # 2. Logic A: Confirm Order
                    if text.upper() == "CONFIRM":
                        row = await conn.fetchrow("DELETE FROM pending_orders WHERE chat_id=$1 AND business_id=$2 RETURNING order_data", chat_id, b_id)
                        if row:
                            d = json.loads(row['order_data'])
                            h = hashlib.md5(f"{chat_id}:{row['order_data']}".encode()).hexdigest()
                            await conn.execute("""
                                INSERT INTO orders (business_id, chat_id, customer_name, phone_no, address, items, total_price, payment_method, status, order_hash)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9) 
                                ON CONFLICT (order_hash) DO NOTHING
                            """, b_id, chat_id, d.get('customer_name'), d.get('phone_no'), d.get('address'), json.dumps(d.get('items')), d.get('total_price'), d.get('payment_method', 'COD'), h)
                            await send(token, chat_id, "✅ *Order Confirmed!*\nအော်ဒါတင်ခြင်း အောင်မြင်ပါသည်။ ဆိုင်မှ မကြာမီ ဆက်သွယ်ပေးပါမည်။")
                        else:
                            await send(token, chat_id, "⚠️ အတည်ပြုရန် အော်ဒါမရှိသေးပါ။")

                    # 3. Logic B: AI Chat & Gathering Details
                    else:
                        menu_rows = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                        menu_text = "\n".join([f"- {m['name']}: {m['price']} MMK" for m in menu_rows])
                        pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2", chat_id, b_id)
                        
                        # AI Processing
                        res = await ai.process(text, shop_name, menu_text, pending['order_data'] if pending else "{}")
                        
                        if res.get('final_order_data'):
                            valid_items, total = validate(res['final_order_data'].get('items', []), menu_rows)
                            res['final_order_data']['items'] = valid_items
                            res['final_order_data']['total_price'] = total

                            # ⚠️ IMPROVED: Upsert Logic to avoid "Already Exists" error
                            await conn.execute("""
                                INSERT INTO pending_orders (chat_id, business_id, order_data, updated_at) 
                                VALUES ($1, $2, $3, NOW())
                                ON CONFLICT (chat_id, business_id) 
                                DO UPDATE SET order_data = EXCLUDED.order_data, updated_at = NOW()
                            """, chat_id, b_id, json.dumps(res['final_order_data']))

                            if res.get('intent') == "confirm_order" and valid_items:
                                p_method = res['final_order_data'].get('payment_method', 'COD')
                                summary = f"📝 *အော်ဒါ အကျဉ်းချုပ်*\n\n👤 အမည်: {res['final_order_data'].get('customer_name')}\n📞 ဖုန်း: {res['final_order_data'].get('phone_no')}\n📍 လိပ်စာ: {res['final_order_data'].get('address')}\n💳 ငွေချေစနစ်: {p_method}\n----------------------\n"
                                for item in valid_items: 
                                    summary += f"- {item['name']} x {item['qty']} ({item['price'] * item['qty']} MMK)\n"
                                summary += f"\n💰 *စုစုပေါင်း: {total} MMK*\n\n"
                                if p_method == "Pre-paid": 
                                    summary += "⚠️ *ငွေလွှဲပြေစာကို Admin ထံ ပို့ပေးပါရန်။*\n\n"
                                summary += "အတည်ပြုရန် 'CONFIRM' ဟု ပို့ပေးပါခင်ဗျာ။"
                                await send(token, chat_id, summary)
                            else:
                                await send(token, chat_id, res.get('reply_text', "ဟုတ်ကဲ့။"))
                        else:
                            await send(token, chat_id, res.get('reply_text', "ဘာများ မှာယူဦးမလဲခင်ဗျာ?"))

                    # Mark Task as Done
                    await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", task['id'])

                except Exception as e:
                    print(f"Task Execution Error: {e}")
                    await conn.execute("UPDATE task_queue SET status='failed', last_error=$1 WHERE id=$2", str(e), task['id'])

        except Exception as outer_e:
            print(f"Worker Loop Error: {outer_e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_worker())
