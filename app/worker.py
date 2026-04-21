import asyncio, json, hashlib, httpx
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    await http_client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": int(chat_id), "text": text, "parse_mode": "HTML"}
    )

def validate(items, menu):
    valid = []
    total = 0

    menu_dict = {m['name'].lower(): m['price'] for m in menu}

    for i in items:
        name = i.get('name', '').lower()
        if name in menu_dict:
            qty = max(1, int(i.get('qty', 1)))
            price = menu_dict[name]
            valid.append({"name": name, "qty": qty, "price": price})
            total += qty * price

    return valid, total

async def run_worker():
    pool = await get_db_pool()
    print("🔥 Worker running...")

    while True:
        async with pool.acquire() as conn:

            task = await conn.fetchrow("""
            UPDATE task_queue SET status='processing'
            WHERE id = (
                SELECT id FROM task_queue
                WHERE status='pending'
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
            """)

            if not task:
                await asyncio.sleep(1)
                continue

            b_id = task['business_id']
            chat_id = task['chat_id']
            text = task['user_text']

            biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)

            token = biz['tg_bot_token']
            shop = biz['shop_name']

            # CONFIRM
            if text.lower() in ["confirm", "ok", "အတည်ပြု"]:
                row = await conn.fetchrow("""
                DELETE FROM pending_orders 
                WHERE chat_id=$1 AND business_id=$2 
                RETURNING order_data
                """, chat_id, b_id)

                if row:
                    d = json.loads(row['order_data'])
                    h = hashlib.md5(str(d).encode()).hexdigest()

                    await conn.execute("""
                    INSERT INTO orders 
                    (business_id, chat_id, customer_name, phone_no, address, items, total_price, payment_method, order_hash)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    ON CONFLICT DO NOTHING
                    """,
                    b_id, chat_id,
                    d['customer_name'], d['phone_no'], d['address'],
                    json.dumps(d['items']), d['total_price'],
                    d['payment_method'], h)

                    await send(token, chat_id, "✅ Order Confirmed")
                else:
                    await send(token, chat_id, "⚠️ No pending order")

            else:
                menu_rows = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                menu = [{"name": m["name"], "price": m["price"]} for m in menu_rows]

                pending = await conn.fetchrow("""
                SELECT order_data FROM pending_orders 
                WHERE chat_id=$1 AND business_id=$2
                """, chat_id, b_id)

                res = await ai.process(text, shop, menu, pending['order_data'] if pending else "{}")

                valid_items, total = validate(res['final_order_data'].get('items', []), menu)

                res['final_order_data']['items'] = valid_items
                res['final_order_data']['total_price'] = total

                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data)
                VALUES ($1,$2,$3)
                ON CONFLICT (chat_id,business_id)
                DO UPDATE SET order_data=$3
                """, chat_id, b_id, json.dumps(res['final_order_data']))

                if res['intent'] == "confirm_order" and valid_items:
                    summary = f"🧾 Order Summary\nTotal: {total}\nType CONFIRM"
                    await send(token, chat_id, summary)
                else:
                    await send(token, chat_id, res['reply_text'])

            await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", task['id'])
