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
    for i in items:
        for m in menu:
            if m['name'].lower() == i.get('name','').lower():
                qty = max(1, int(i.get('qty', 1)))
                valid.append({
                    "name": m['name'], 
                    "qty": qty, 
                    "price": m['price']
                })
                total += qty * m['price']
    return valid, total

async def run_worker():
    # --- ပြင်ဆင်ချက်: Database Pool ကို Cache မပါဘဲ ယူမယ် ---
    # get_db_pool ထဲမှာ statement_cache_size=0 ထည့်ထားဖို့ လိုပါတယ်
    pool = await get_db_pool(for_worker=True)
    print("Worker is running and watching for tasks...")

    while True:
        try:
            async with pool.acquire() as conn:
                # 1. Task Queue ထဲက အသစ်တစ်ခုကို ဆွဲထုတ်ပြီး processing ပြောင်းမယ်
                # schema ပြောင်းထားတဲ့အတွက် created_at နဲ့ updated_at ကို သေချာစစ်မယ်
                task = await conn.fetchrow("""
                    UPDATE task_queue 
                    SET status='processing', updated_at = NOW()
                    WHERE id = (
                        SELECT id FROM task_queue 
                        WHERE status='pending' 
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

                # 2. ဆိုင်ရဲ့ အချက်အလက်ကို ယူမယ်
                biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)
                if not biz:
                    print(f"Business {b_id} not found.")
                    await conn.execute("UPDATE task_queue SET status='failed', last_error='Business not found' WHERE id=$1", task['id'])
                    continue

                try:
                    # --- Logic A: Order Confirmation ---
                    if text == "CONFIRM":
                        async with conn.transaction():
                            row = await conn.fetchrow("""
                                DELETE FROM pending_orders 
                                WHERE chat_id=$1 AND business_id=$2 
                                RETURNING order_data
                            """, chat_id, b_id)

                            if row:
                                d = json.loads(row['order_data'])
                                h = hashlib.md5(str(d).encode()).hexdigest()

                                await conn.execute("""
                                    INSERT INTO orders (business_id, customer_name, phone_no, address, items, total_price, order_hash)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                                    ON CONFLICT (order_hash) DO NOTHING
                                """, b_id, d.get('name', 'Customer'), d.get('phone'), d.get('address'), 
                                     json.dumps(d.get('items')), d.get('total'), h)

                                await send(biz['tg_bot_token'], chat_id, "✅ Order confirmed! ဆိုင်မှ မကြာမီ ဆက်သွယ်ပေးပါမည်။")
                            else:
                                await send(biz['tg_bot_token'], chat_id, "⚠️ အတည်ပြုရန် Order မရှိသေးပါ။")

                    # --- Logic B: AI Processing ---
                    else:
                        menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                        res = await ai.process(text, biz['shop_name'], menu)

                        if res.get('intent') == "confirm_order":
                            items, total = validate(res['final_order_data'].get('items', []), menu)
                            
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
                                    summary += f"- {item['name']} x {item['qty']}\n"
                                summary += f"\n💰 စုစုပေါင်း: {total} MMK\n\nအတည်ပြုရန် 'CONFIRM' ဟု ရိုက်ပေးပါ။"
                                
                                await send(biz['tg_bot_token'], chat_id, summary)
                            else:
                                await send(biz['tg_bot_token'], chat_id, "❌ ဆိုင်မှာမရှိတဲ့ item တွေဖြစ်နေလို့ အော်ဒါတင်မရပါ။")
                        else:
                            await send(biz['tg_bot_token'], chat_id, res['reply_text'])

                    # Task ပြီးဆုံးကြောင်း မှတ်မယ်
                    await conn.execute("UPDATE task_queue SET status='done', updated_at = NOW() WHERE id=$1", task['id'])

                except Exception as inner_e:
                    error_msg = str(inner_e)
                    print(f"Inner Logic Error: {error_msg}")
                    await conn.execute("UPDATE task_queue SET status='pending', last_error=$1, updated_at = NOW() WHERE id=$2", error_msg, task['id'])
                    await asyncio.sleep(2)

        except asyncpg.InternalClientError:
            # Schema ပြောင်းသွားချိန်မှာဖြစ်တဲ့ error အတွက် pool ကို refresh လုပ်ဖို့ ကြိုးစားမယ်
            print("Database schema changed. Refreshing connection...")
            await asyncio.sleep(2)
        except Exception as outer_e:
            print(f"Worker Loop Error: {outer_e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_worker())
