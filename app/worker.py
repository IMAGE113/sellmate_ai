import asyncio
import json
import hashlib
import os
import httpx
import asyncpg
from .database import get_db_pool
from .ai import ai

# Global HTTP Client (Timeout ကို ၁၅ စက္ကန့်ထိ တိုးထားပါတယ်)
http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    try:
        # Markdown parsing error မတက်အောင် သတိထားရမယ်
        await http_client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        )
    except Exception as e:
        print(f"Telegram Send Error: {e}")

def validate(items, menu):
    valid = []
    total = 0
    menu_dict = {m['name'].lower(): m['price'] for m in menu}
    
    if not items or not isinstance(items, list):
        return valid, total

    for i in items:
        if not isinstance(i, dict): continue
        name = i.get('name', '').lower()
        if name in menu_dict:
            try:
                qty = max(1, int(i.get('qty', 1)))
                price = menu_dict[name]
                valid.append({
                    "name": i.get('name'), 
                    "qty": qty, 
                    "price": price
                })
                total += qty * price
            except:
                continue
    return valid, total

async def run_worker():
    pool = await get_db_pool(for_worker=True)
    print("Worker is running and watching for tasks...")

    while True:
        try:
            async with pool.acquire() as conn:
                # Task ယူမယ့် SQL (Attempts စစ်ထားတယ်)
                task = await conn.fetchrow("""
                    UPDATE task_queue 
                    SET status='processing', attempts = attempts + 1, updated_at = NOW()
                    WHERE id = (
                        SELECT id FROM task_queue 
                        WHERE status IN ('pending', 'failed') AND attempts < 5
                        ORDER BY created_at ASC 
                        LIMIT 1 FOR UPDATE SKIP LOCKED
                    )
                    RETURNING *
                """)

                if not task:
                    await asyncio.sleep(1)
                    continue

                print(f"DEBUG: Processing Task ID {task['id']} for Chat ID {task['chat_id']}")

                b_id = task['business_id']
                chat_id = task['chat_id']
                text = task['user_text']

                biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)
                if not biz:
                    await conn.execute("UPDATE task_queue SET status='failed', last_error='Business not found' WHERE id=$1", task['id'])
                    continue

                token = biz['tg_bot_token']

                try:
                    # --- Logic A: Order Confirmation ---
                    if text.strip().upper() == "CONFIRM":
                        row = await conn.fetchrow("""
                            DELETE FROM pending_orders 
                            WHERE chat_id=$1 AND business_id=$2 
                            RETURNING order_data
                        """, chat_id, b_id)

                        if row:
                            d = json.loads(row['order_data'])
                            h = hashlib.md5(f"{chat_id}:{row['order_data']}".encode()).hexdigest()

                            await conn.execute("""
                                INSERT INTO orders (business_id, customer_name, phone_no, address, items, total_price, order_hash)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ON CONFLICT (order_hash) DO NOTHING
                            """, b_id, d.get('customer_name'), d.get('phone_no'), d.get('address'), 
                                 json.dumps(d.get('items')), d.get('total_price'), h)

                            await send(token, chat_id, "✅ *Order confirmed!* အော်ဒါတင်ခြင်း အောင်မြင်ပါသည်။ ကျေးဇူးတင်ပါတယ်ခင်ဗျာ။")
                        else:
                            await send(token, chat_id, "⚠️ အတည်ပြုရန် အော်ဒါမရှိသေးပါ။ အရင်ဆုံး စာရင်းပေးပေးပါ။")

                    # --- Logic B: AI Processing ---
                    else:
                        menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                        menu_text = "\n".join([f"- {m['name']}: {m['price']} MMK" for m in menu])
                        
                        pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2", chat_id, b_id)
                        history = pending['order_data'] if pending else "{}"

                        # AI ကို ခေါ်မယ် (ဒီမှာ Stuck ဖြစ်နိုင်ခြေအများဆုံးပဲ)
                        res = await ai.process(text, biz['shop_name'], menu_text, history)
                        
                        print(f"DEBUG: AI Intent -> {res.get('intent')}")

                        # final_order_data ရှိရင် database မှာ သိမ်းမယ်
                        if res.get('final_order_data'):
                            await conn.execute("""
                                INSERT INTO pending_orders (chat_id, business_id, order_data, updated_at)
                                VALUES ($1, $2, $3, NOW())
                                ON CONFLICT (chat_id, business_id) 
                                DO UPDATE SET order_data=$3, updated_at=NOW()
                            """, chat_id, b_id, json.dumps(res['final_order_data']))

                        # Intent အလိုက် စာပြန်မယ်
                        if res.get('intent') == "confirm_order":
                            items, total = validate(res['final_order_data'].get('items', []), menu)
                            
                            if items:
                                summary = f"📝 **အော်ဒါ အကျဉ်းချုပ်**\n\n"
                                summary += f"👤 အမည်: {res['final_order_data'].get('customer_name')}\n"
                                summary += f"📞 ဖုန်း: {res['final_order_data'].get('phone_no')}\n"
                                summary += f"📍 လိပ်စာ: {res['final_order_data'].get('address')}\n"
                                summary += f"--- မှာယူသည့်ပစ္စည်းများ ---\n"
                                for item in items:
                                    summary += f"- {item['name']} x {item['qty']} ({item['price'] * item['qty']} ကျပ်)\n"
                                summary += f"\n💰 **စုစုပေါင်း: {total} MMK**\n\nအတည်ပြုရန် 'CONFIRM' ဟု ပြန်ပို့ပေးပါခင်ဗျာ။"
                                await send(token, chat_id, summary)
                            else:
                                await send(token, chat_id, "❌ ဆိုင်ရဲ့ Menu ထဲက ပစ္စည်းတွေကိုပဲ မှာယူလို့ရပါတယ်။ ဘာများ ထပ်ယူမလဲခင်ဗျာ?")
                        else:
                            reply = res.get('reply_text', "နားမလည်လို့ပါခင်ဗျာ။ ပြန်ပြောပြပေးပါဦး။")
                            await send(token, chat_id, reply)

                    # အောင်မြင်ရင် task ကို 'done' လုပ်မယ်
                    await conn.execute("UPDATE task_queue SET status='done', updated_at = NOW() WHERE id=$1", task['id'])
                    print(f"DEBUG: Task {task['id']} finished successfully.")

                except Exception as inner_e:
                    print(f"WORKER INNER ERROR: {inner_e}")
                    await conn.execute("UPDATE task_queue SET status='failed', last_error=$1, updated_at = NOW() WHERE id=$2", str(inner_e), task['id'])

        except Exception as outer_e:
            print(f"WORKER LOOP ERROR: {outer_e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_worker())
