import asyncio, json, hashlib, httpx
from datetime import datetime
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    if not text:
        text = "ဘာများ မှာယူမလဲခင်ဗျာ?"

    try:
        await http_client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(chat_id), "text": text}
        )
        await asyncio.sleep(0.05)
    except Exception as e:
        print("TG error:", e)


def validate(items, menu):
    valid, total = [], 0
    menu_dict = {m["name"].lower(): m["price"] for m in menu}

    for i in items or []:
        name = i.get("name", "").lower()
        if name in menu_dict:
            qty = max(1, int(i.get("qty", 1)))
            price = menu_dict[name]
            valid.append({"name": name, "qty": qty, "price": price})
            total += qty * price

    return valid, total


async def run_worker():
    pool = await get_db_pool()
    print("🔥 Worker running...")

    while True:
        try:
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

                b_id, chat_id, text = task['business_id'], task['chat_id'], task['user_text']

                biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)
                if not biz:
                    continue

                token = biz['tg_bot_token']

                # CONFIRM FLOW
                if text.upper() == "CONFIRM":

                    row = await conn.fetchrow("""
                    DELETE FROM pending_orders
                    WHERE chat_id=$1 AND business_id=$2
                    RETURNING order_data
                    """, chat_id, b_id)

                    if not row:
                        await send(token, chat_id, "⚠️ အော်ဒါမရှိပါ")
                        continue

                    data = json.loads(row['order_data'])

                    sub = await conn.fetchrow("""
                    UPDATE subscriptions
                    SET current_usage = current_usage + 1
                    WHERE business_id=$1
                    RETURNING *
                    """, b_id)

                    if not sub:
                        await send(token, chat_id, "⚠️ subscription မရှိပါ")
                        continue

                    h = hashlib.md5(f"{chat_id}:{row['order_data']}".encode()).hexdigest()

                    await conn.execute("""
                    INSERT INTO orders (
                        business_id, chat_id,
                        customer_name, phone_no, address,
                        payment_method, items, total_price, order_hash
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    """,
                    b_id, chat_id,
                    data.get('customer_name'),
                    data.get('phone_no'),
                    data.get('address'),
                    data.get('payment_method'),
                    json.dumps(data.get('items')),
                    data.get('total_price',0),
                    h
                    )

                    await send(token, chat_id, "✅ Order confirmed!")
                    continue

                # NORMAL FLOW
                menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                menu_list = [{"name": m["name"], "price": m["price"]} for m in menu]

                pending = await conn.fetchrow("""
                SELECT order_data FROM pending_orders
                WHERE chat_id=$1 AND business_id=$2
                """, chat_id, b_id)

                try:
                    current_order = json.loads(pending['order_data']) if pending else {}
                except:
                    current_order = {}

                res = await ai.process(text, biz['name'], menu_list, current_order)

                valid_items, total = validate(res['final_order_data'].get('items', []), menu_list)

                res['final_order_data']['items'] = valid_items
                res['final_order_data']['total_price'] = total

                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data)
                VALUES ($1,$2,$3)
                ON CONFLICT (chat_id, business_id)
                DO UPDATE SET order_data=$3
                """, chat_id, b_id, json.dumps(res['final_order_data']))

                await send(token, chat_id, res['reply_text'])

        except Exception as e:
            print("Worker crash:", e)
            await asyncio.sleep(3)
