import asyncio, json, hashlib, httpx
from datetime import datetime
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    if not text:
        text = "ဘာများ မှာယူမလဲခင်ဗျာ?"
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = await http_client.post(
            url,
            json={"chat_id": int(chat_id), "text": text}
        )
        if res.status_code != 200:
            print(f"TG Error Status: {res.status_code} - {res.text}")
        await asyncio.sleep(0.05)
    except Exception as e:
        print("TG error:", e)

def validate(items, menu):
    valid, total = [], 0
    menu_dict = {m["name"].lower(): m["price"] for m in menu}

    for i in items or []:
        name = i.get("name", "").lower().strip()
        if name in menu_dict:
            try:
                qty = max(1, int(i.get("qty", 1)))
                price = menu_dict[name]
                valid.append({"name": name, "qty": qty, "price": price})
                total += qty * price
            except: continue
    return valid, total

async def run_worker():
    pool = await get_db_pool()
    print("🚀 SellMate Worker is officially running...")

    while True:
        try:
            async with pool.acquire() as conn:
                # 1. Get Pending Task
                task = await conn.fetchrow("""
                UPDATE task_queue SET status='processing'
                WHERE id = (
                    SELECT id FROM task_queue
                    WHERE status='pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
                """)

                if not task:
                    await asyncio.sleep(1)
                    continue

                task_id = task['id']
                b_id, chat_id, text = task['business_id'], task['chat_id'], task['user_text']

                # 2. Get Business Info
                biz = await conn.fetchrow("SELECT name, tg_bot_token FROM businesses WHERE id=$1", b_id)
                if not biz:
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task_id)
                    continue

                token = biz['tg_bot_token']

                # 3. Handle CONFIRM Flow
                if text and text.upper().strip() == "CONFIRM":
                    row = await conn.fetchrow("""
                    DELETE FROM pending_orders 
                    WHERE chat_id=$1 AND business_id=$2
                    RETURNING order_data
                    """, str(chat_id), b_id)

                    if not row:
                        await send(token, chat_id, "⚠️ အော်ဒါမှတ်တမ်း မရှိပါခင်ဗျာ။")
                    else:
                        data = json.loads(row['order_data'])
                        
                        # ✅ CTO FIX: Invalid format specifier error ကာကွယ်ဖို့ concatenation သုံးမယ်
                        order_str = str(row['order_data'])
                        hash_input = str(chat_id) + ":" + order_str + ":" + str(datetime.now())
                        h = hashlib.md5(hash_input.encode()).hexdigest()
                        
                        await conn.execute("""
                        INSERT INTO orders (business_id, chat_id, customer_name, phone_no, address, payment_method, items, total_price, order_hash)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        ON CONFLICT DO NOTHING
                        """, b_id, str(chat_id), data.get('customer_name'), data.get('phone_no'), data.get('address'), data.get('payment_method'), json.dumps(data.get('items')), data.get('total_price', 0), h)
                        
                        await send(token, chat_id, "✅ အော်ဒါတင်ခြင်း အောင်မြင်သွားပါပြီ။ ကျေးဇူးတင်ပါတယ်ခင်ဗျာ!")
                    
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task_id)
                    continue

                # 4. Normal AI Process Flow
                menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                menu_list = [{"name": m["name"], "price": m["price"]} for m in menu]

                pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2", str(chat_id), b_id)
                current_order = json.loads(pending['order_data']) if pending else {}

                # AI Processing
                res = await ai.process(text, biz['name'], menu_list, current_order)

                # Validation & Update
                valid_items, total = validate(res['final_order_data'].get('items', []), menu_list)
                res['final_order_data']['items'] = valid_items
                res['final_order_data']['total_price'] = total

                # Save Pending State
                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data, updated_at)
                VALUES ($1,$2,$3, NOW())
                ON CONFLICT (chat_id, business_id)
                DO UPDATE SET order_data=$3, updated_at=NOW()
                """, str(chat_id), b_id, json.dumps(res['final_order_data']))

                # 5. Send Result to Telegram
                await send(token, chat_id, res['reply_text'])

                # Task ကို ပြီးသွားကြောင်း ဖျက်ပစ်
                await conn.execute("DELETE FROM task_queue WHERE id=$1", task_id)

        except Exception as e:
            print(f"🔥 Worker Error at {datetime.now()}: {e}")
            # Error ဖြစ်တဲ့ task ကို ပြန်စစ်နိုင်အောင် Status ပြန်ပြင်ပေးမယ်
            try:
                if 'task_id' in locals():
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE task_queue SET status='pending' WHERE id=$1", task_id)
            except: pass
            await asyncio.sleep(2)
