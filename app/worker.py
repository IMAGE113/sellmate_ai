import asyncio, json, hashlib, httpx
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    await http_client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": int(chat_id), "text": text}
    )

def validate(items, menu):
    valid, total = [], 0
    menu_dict = {m['name'].lower(): m['price'] for m in menu}

    for i in items:
        name = i.get('name','').lower()
        if name in menu_dict:
            qty = max(1, int(i.get('qty',1)))
            price = menu_dict[name]
            valid.append({"name": name, "qty": qty, "price": price})
            total += qty * price

    return valid, total

async def run_worker():
    pool = await get_db_pool(for_worker=True)
    print("Worker running...")

    while True:
        async with pool.acquire() as conn:
            task = await conn.fetchrow("""
                UPDATE task_queue SET status='processing'
                WHERE id = (
                    SELECT id FROM task_queue
                    WHERE status='pending'
                    LIMIT 1 FOR UPDATE SKIP LOCKED
                )
                RETURNING *
            """)

            if not task:
                await asyncio.sleep(1)
                continue

            b_id, chat_id, text = task['business_id'], task['chat_id'], task['user_text']
            biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)

            token = biz['tg_bot_token']
            shop = biz['shop_name']

            if text.upper() == "CONFIRM":
                row = await conn.fetchrow("""
                    DELETE FROM pending_orders
                    WHERE chat_id=$1 AND business_id=$2
                    RETURNING order_data
                """, chat_id, b_id)

                if row:
                    d = json.loads(row['order_data'])
                    await send(token, chat_id, "✅ Order confirmed")
                else:
                    await send(token, chat_id, "⚠️ No order")

            else:
                menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)

                pending = await conn.fetchrow("""
                    SELECT order_data FROM pending_orders
                    WHERE chat_id=$1 AND business_id=$2
                """, chat_id, b_id)

                history = json.loads(pending['order_data']) if pending else {}

                res = await ai.process(text, shop, [dict(m) for m in menu], history)

                valid_items, total = validate(res['final_order_data']['items'], menu)
                res['final_order_data']['items'] = valid_items
                res['final_order_data']['total_price'] = total

                await conn.execute("""
                    INSERT INTO pending_orders (chat_id, business_id, order_data)
                    VALUES ($1,$2,$3)
                    ON CONFLICT (chat_id,business_id)
                    DO UPDATE SET order_data=$3
                """, chat_id, b_id, json.dumps(res['final_order_data']))

                await send(token, chat_id, res['reply_text'])

            await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", task['id'])
