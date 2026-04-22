import asyncio, json, hashlib, httpx
from datetime import datetime
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    if not text:
        text = "ဘာများ မှာယူမလဲခင်ဗျာ?"
    try:
        url = "https://api.telegram.org/bot" + str(token) + "/sendMessage"
        # Type mismatch မဖြစ်အောင် explicit convert လုပ်မယ်
        payload = {"chat_id": int(chat_id), "text": str(text)}
        await http_client.post(url, json=payload)
        await asyncio.sleep(0.05)
    except Exception as e:
        print("TG error: " + str(e))

def validate(items, menu):
    valid, total = [], 0
    menu_dict = {m["name"].lower(): m["price"] for m in menu}
    for i in items or []:
        name = str(i.get("name", "")).lower().strip()
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
                # Task ဆွဲထုတ်ခြင်း
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
                b_id = task['business_id']
                # အဓိက Fix: Chat ID ကို integer သေချာပြောင်း
                clean_chat_id = int(task['chat_id'])
                text = str(task['user_text'])

                biz = await conn.fetchrow("SELECT name, tg_bot_token FROM businesses WHERE id=$1", b_id)
                if not biz:
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task_id)
                    continue

                token = biz['tg_bot_token']

                # --- 1. CONFIRMATION LOGIC ---
                if text.upper().strip() == "CONFIRM":
                    row = await conn.fetchrow("DELETE FROM pending_orders WHERE chat_id=$1 AND business_id=$2 RETURNING order_data", clean_chat_id, b_id)
                    if not row:
                        await send(token, clean_chat_id, "⚠️ အော်ဒါမှတ်တမ်း မရှိပါခင်ဗျာ။")
                    else:
                        data = json.loads(row['order_data'])
                        # f-string ကို လုံးဝမသုံးဘဲ string ဆက်မယ် (Format Error ကာကွယ်ရန်)
                        hash_input = str(clean_chat_id) + ":" + str(row['order_data']) + ":" + str(datetime.now())
                        h = hashlib.md5(hash_input.encode()).hexdigest()
                        
                        await conn.execute("""
                        INSERT INTO orders (business_id, chat_id, customer_name, phone_no, address, payment_method, items, total_price, order_hash)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        """, b_id, clean_chat_id, data.get('customer_name'), data.get('phone_no'), data.get('address'), data.get('payment_method'), json.dumps(data.get('items')), data.get('total_price', 0), h)
                        
                        await send(token, clean_chat_id, "✅ အော်ဒါတင်ခြင်း အောင်မြင်သွားပါပြီ။ ကျေးဇူးတင်ပါတယ်ခင်ဗျာ!")
                    
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task_id)
                    continue

                # --- 2. AI PROCESSING ---
                menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                menu_list = [{"name": m["name"], "price": m["price"]} for m in menu]

                pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2", clean_chat_id, b_id)
                current_order = json.loads(pending['order_data']) if pending else {}

                res = await ai.process(text, biz['name'], menu_list, current_order)
                
                # Order data validation
                final_data = res.get('final_order_data', {})
                valid_items, total = validate(final_data.get('items', []), menu_list)
                final_data['items'] = valid_items
                final_data['total_price'] = total

                # --- 3. SAVE & REPLY ---
                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data, updated_at)
                VALUES ($1,$2,$3, NOW())
                ON CONFLICT (chat_id, business_id)
                DO UPDATE SET order_data=$3, updated_at=NOW()
                """, clean_chat_id, b_id, json.dumps(final_data))

                await send(token, clean_chat_id, res.get('reply_text', "နားမလည်လိုက်ပါဘူးခင်ဗျာ။"))
                await conn.execute("DELETE FROM task_queue WHERE id=$1", task_id)

        except Exception as e:
            # f-string ကို လုံးဝမသုံးတော့ဘဲ log ထုတ်မယ်
            print("🔥 Worker Error: " + str(e))
            if 'task_id' in locals():
                try:
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE task_queue SET status='pending' WHERE id=$1", task_id)
                except: pass
            await asyncio.sleep(2)
