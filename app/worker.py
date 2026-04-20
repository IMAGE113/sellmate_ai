import asyncio
import json
import hashlib
import os
import httpx
import asyncpg
from .database import get_db_pool
from .ai import ai

# Global HTTP Client
http_client = httpx.AsyncClient(timeout=10.0)

async def send(token, chat_id, text):
    try:
        await http_client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram Send Error: {e}")

def validate(items, menu):
    valid = []
    total = 0
    # Menu ကို dict အဖြစ်ပြောင်းလိုက်ရင် ပိုမြန်တယ်
    menu_dict = {m['name'].lower(): m['price'] for m in menu}
    
    for i in items:
        name = i.get('name', '').lower()
        if name in menu_dict:
            qty = max(1, int(i.get('qty', 1)))
            price = menu_dict[name]
            valid.append({
                "name": i.get('name'), 
                "qty": qty, 
                "price": price
            })
            total += qty * price
    return valid, total

async def run_worker():
    # statement_cache_size=0 ပါတဲ့ pool ကို ယူမယ်
    pool = await get_db_pool(for_worker=True)
    print("Worker is running and watching for tasks...")

    while True:
        try:
            async with pool.acquire() as conn:
                # 1. Task ဆွဲထုတ်မယ် (Attempts 5 ကြိမ်ထက်နည်းတာပဲ ယူမယ်)
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

                b_id = task['business_id']
                chat_id = task['chat_id']
                text = task['user_text']

                # 2. ဆိုင်ရဲ့ Token နဲ့ အချက်အလက်ယူမယ်
                biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)
                if not biz:
                    await conn.execute("UPDATE task_queue SET status='failed', last_error='Business not found' WHERE id=$1", task['id'])
                    continue

                token = biz['tg_bot_token']

                try:
                    # --- Logic A: Order Confirmation ---
                    if text.upper() == "CONFIRM":
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
                            """, b_id, d.get('name', 'Customer'), d.get('phone'), d.get('address'), 
                                 json.dumps(d.get('items')), d.get('total'), h)

                            await send(token, chat_id, "✅ Order confirmed! အော်ဒါတင်ခြင်း အောင်မြင်ပါသည်။")
                        else:
                            await send(token, chat_id, "⚠️ အတည်ပြုရန် အော်ဒါမရှိသေးပါ။ အရင်ဆုံး စာရင်းပေးပေးပါ။")

                    # --- Logic B: AI Processing ---
                    else:
                        menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                        # AI ဆီပို့မယ်
                        res = await ai.process(text, biz['shop_name'], menu)

                        if res.get('intent') == "confirm_order":
                            items, total = validate(res.get('final_order_data', {}).get('items', []), menu)
                            
                            if items:
                                res['final_order_data']['items'] = items
                                res['final_order_data']['total'] = total

                                await conn.execute("""
                                    INSERT INTO pending_orders (chat_id, business_id, order_data, updated_at)
                                    VALUES ($1, $2, $3, NOW())
                                    ON CONFLICT (chat_id, business_id) 
                                    DO UPDATE SET order_data=$3, updated_at=NOW()
                                """, chat_id, b_id, json.dumps(res['final_order_data']))

                                summary = f"📝 **Order Summary**\n"
                                for item in items:
                                    summary += f"- {item['name']} x {item['qty']} ({item['price']} ကျပ်)\n"
                                summary += f"\n💰 စုစုပေါင်း: {total} MMK\n\nအတည်ပြုရန် 'CONFIRM' ဟု ပြန်ပို့ပေးပါ။"
                                await send(token, chat_id, summary)
                            else:
                                await send(token, chat_id, "❌ စိတ်မရှိပါနဲ့၊ ဆိုင်ရဲ့ Menu ထဲက ပစ္စည်းတွေကိုပဲ မှာယူလို့ရပါတယ်။")
                        else:
                            # ပုံမှန် စကားပြောဆိုမှုများ
                            reply = res.get('reply_text', "နားမလည်လို့ပါခင်ဗျာ။ ပြန်ပြောပြပေးပါဦး။")
                            await send(token, chat_id, reply)

                    # အောင်မြင်ကြောင်းမှတ်မယ်
                    await conn.execute("UPDATE task_queue SET status='done', updated_at = NOW() WHERE id=$1", task['id'])

                except Exception as inner_e:
                    print(f"Inner Error: {inner_e}")
                    await conn.execute("UPDATE task_queue SET status='failed', last_error=$1, updated_at = NOW() WHERE id=$2", str(inner_e), task['id'])

        except Exception as outer_e:
            print(f"Worker Loop Error: {outer_e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_worker())
