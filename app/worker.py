import asyncio, json, httpx
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=30.0)

async def send_telegram(token, chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": str(chat_id), "text": text, "parse_mode": "HTML"}
        print(f"📡 Sending to TG: {chat_id} | Token: {token[:10]}...") # Debug log
        
        resp = await http_client.post(url, json=payload)
        result = resp.json()
        
        if not result.get("ok"):
            print(f"❌ TG API Error: {result.get('description')}")
        else:
            print(f"✅ TG Message Sent Successfully to {chat_id}")
        return result
    except Exception as e:
        print(f"❌ Telegram Network Error: {e}")

def validate_items(items, menu):
    valid = []
    total = 0
    menu_dict = {m['name'].lower(): m['price'] for m in menu}
    for i in items:
        name = str(i.get('name', '')).lower()
        if name in menu_dict:
            qty = max(1, int(i.get('qty', 1)))
            price = menu_dict[name]
            valid.append({"name": name, "qty": qty, "price": price})
            total += qty * price
    return valid, total

async def run_worker():
    pool = await get_db_pool()
    print("🔥 Worker is active and listening...")

    while True:
        try:
            async with pool.acquire() as conn:
                task = await conn.fetchrow("""
                UPDATE task_queue SET status='processing'
                WHERE id = (
                    SELECT id FROM task_queue
                    WHERE status='pending'
                    ORDER BY id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, business_id, chat_id, user_text
                """)

                if not task:
                    await asyncio.sleep(2)
                    continue

                b_id, chat_id, text = task['business_id'], task['chat_id'], task['user_text']
                
                # ဆိုင်အချက်အလက် ယူမယ်
                biz = await conn.fetchrow("SELECT tg_bot_token, shop_name FROM businesses WHERE id=$1", b_id)
                if not biz:
                    await conn.execute("UPDATE task_queue SET status='failed' WHERE id=$1", task['id'])
                    continue

                token, shop_name = biz['tg_bot_token'], biz['shop_name']
                
                # AI Processing
                menu_rows = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                menu = [{"name": m["name"], "price": m["price"]} for m in menu_rows]
                
                pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2", chat_id, b_id)
                current_order_json = pending['order_data'] if pending else "{}"

                res = await ai.process(text, shop_name, menu, current_order_json)
                
                # Update Database
                new_order_data = res.get('final_order_data', {})
                valid_items, total = validate_items(new_order_data.get('items', []), menu)
                new_order_data['items'] = valid_items
                new_order_data['total_price'] = total

                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data)
                VALUES ($1,$2,$3)
                ON CONFLICT (chat_id,business_id)
                DO UPDATE SET order_data=$3
                """, chat_id, b_id, json.dumps(new_order_data))

                # စာပြန်ပို့မယ်
                reply = res.get('reply_text', "Hello!")
                await send_telegram(token, chat_id, reply)

                await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", task['id'])
                print(f"🏁 Task {task['id']} completed.")

        except Exception as e:
            print(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5)
