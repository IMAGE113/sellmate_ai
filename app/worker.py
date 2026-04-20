import asyncio, json, hashlib, os, httpx, time
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=10.0)

async def send(token, chat_id, text):
    await http_client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10
    )

def validate(items, menu):
    valid = []
    total = 0
    for i in items:
        for m in menu:
            if m['name'].lower() == i.get('name','').lower():
                qty = max(1, int(i.get('qty',1)))
                valid.append({"name": m['name'], "qty": qty, "price": m['price']})
                total += qty*m['price']
    return valid, total

async def run_worker():
    pool = await get_db_pool(for_worker=True)

    while True:
        async with pool.acquire() as conn:
            task = await conn.fetchrow("""
            UPDATE task_queue SET status='processing'
            WHERE id = (
                SELECT id FROM task_queue WHERE status='pending'
                LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            RETURNING *
            """)

            if not task:
                await asyncio.sleep(1)
                continue

            b_id, chat_id, text = task['business_id'], task['chat_id'], task['user_text']
            biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)

            try:
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
                            INSERT INTO orders (business_id,customer_name,phone_no,address,items,total_price,order_hash)
                            VALUES ($1,$2,$3,$4,$5,$6,$7)
                            ON CONFLICT DO NOTHING
                            """, b_id, d['name'], d['phone'], d['address'],
                                 json.dumps(d['items']), d['total'], h)

                            await send(biz['tg_bot_token'], chat_id, "✅ Order confirmed")

                else:
                    menu = await conn.fetch("SELECT name,price FROM products WHERE business_id=$1", b_id)
                    res = await ai.process(text, biz['shop_name'], menu)

                    if res['intent'] == "confirm_order":
                        items, total = validate(res['final_order_data']['items'], menu)
                        if items:
                            res['final_order_data']['items'] = items
                            res['final_order_data']['total'] = total

                            await conn.execute("""
                            INSERT INTO pending_orders (chat_id,business_id,order_data)
                            VALUES ($1,$2,$3)
                            ON CONFLICT (chat_id,business_id) DO UPDATE SET order_data=$3
                            """, chat_id, b_id, json.dumps(res['final_order_data']))

                            await send(biz['tg_bot_token'], chat_id, "Confirm? type CONFIRM")
                        else:
                            await send(biz['tg_bot_token'], chat_id, "Invalid items")

                    else:
                        await send(biz['tg_bot_token'], chat_id, res['reply_text'])

                await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", task['id'])

            except Exception:
                await conn.execute("UPDATE task_queue SET status='pending' WHERE id=$1", task['id'])
                await asyncio.sleep(2)
