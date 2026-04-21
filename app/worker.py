import asyncio
import json
import hashlib
import os
import httpx
from .database import get_db_pool
from .ai import ai

http_client = httpx.AsyncClient(timeout=15.0)

async def send(token, chat_id, text):
    try:
        await http_client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": int(chat_id),
                "text": text,
                "parse_mode": "Markdown"
            },
        )
    except Exception as e:
        print("Telegram Error:", e)


# ✅ STRICT VALIDATION (anti-hallucination)
def validate(items, menu):
    valid = []
    total = 0

    menu_dict = {
        m['name'].strip().lower(): m['price']
        for m in menu
    }

    for i in items:
        name = i.get('name', '').strip().lower()

        match = next((k for k in menu_dict if name in k or k in name), None)

        if match:
            qty = max(1, int(i.get('qty', 1)))
            price = menu_dict[match]

            valid.append({
                "name": match,
                "qty": qty,
                "price": price
            })
            total += qty * price

    return valid, total


async def run_worker():
    pool = await get_db_pool(for_worker=True)
    print("Worker running...")

    while True:
        try:
            async with pool.acquire() as conn:

                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', attempts = attempts + 1
                    WHERE id = (
                        SELECT id FROM task_queue 
                        WHERE status IN ('pending','failed') AND attempts < 5
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
                text = (task['user_text'] or "").strip()

                biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", b_id)
                if not biz:
                    await conn.execute("UPDATE task_queue SET status='failed' WHERE id=$1", task['id'])
                    continue

                token = biz['tg_bot_token']
                shop_name = biz['shop_name']

                try:
                    # ✅ CONFIRM
                    if text.upper() == "CONFIRM":
                        row = await conn.fetchrow(
                            "DELETE FROM pending_orders WHERE chat_id=$1 AND business_id=$2 RETURNING order_data",
                            chat_id, b_id
                        )

                        if row:
                            d = json.loads(row['order_data'])
                            h = hashlib.md5(f"{chat_id}:{row['order_data']}".encode()).hexdigest()

                            await conn.execute("""
                                INSERT INTO orders (
                                    business_id, chat_id, customer_name, phone_no, address,
                                    items, total_price, payment_method, status, order_hash
                                )
                                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'pending',$9)
                                ON CONFLICT (order_hash) DO NOTHING
                            """,
                            b_id, chat_id,
                            d.get('customer_name'),
                            d.get('phone_no'),
                            d.get('address'),
                            json.dumps(d.get('items')),
                            d.get('total_price'),
                            d.get('payment_method', 'COD'),
                            h
                            )

                            await send(token, chat_id, "✅ Order Confirmed!")
                        else:
                            await send(token, chat_id, "⚠️ No pending order.")

                    # ✅ NORMAL FLOW
                    else:
                        menu_rows = await conn.fetch(
                            "SELECT name, price FROM products WHERE business_id=$1", b_id
                        )

                        menu = [{"name": m["name"], "price": m["price"]} for m in menu_rows]

                        pending = await conn.fetchrow(
                            "SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2",
                            chat_id, b_id
                        )

                        history = pending['order_data'] if pending else "{}"
                        if isinstance(history, dict):
                            history = json.dumps(history)

                        res = await ai.process(text, shop_name, menu, history)

                        data = res.get('final_order_data', {})

                        valid_items, total = validate(data.get('items', []), menu)
                        data['items'] = valid_items
                        data['total_price'] = total

                        await conn.execute("""
                            INSERT INTO pending_orders (chat_id, business_id, order_data)
                            VALUES ($1,$2,$3)
                            ON CONFLICT (chat_id,business_id)
                            DO UPDATE SET order_data=$3
                        """, chat_id, b_id, json.dumps(data))

                        # ✅ CONFIRM STAGE
                        if res.get("intent") == "confirm_order" and valid_items:
                            summary = "🧾 Order Summary\n\n"

                            summary += f"👤 {data.get('customer_name')}\n"
                            summary += f"📞 {data.get('phone_no')}\n"
                            summary += f"📍 {data.get('address')}\n\n"

                            for item in valid_items:
                                summary += f"- {item['name']} x {item['qty']} = {item['price'] * item['qty']} MMK\n"

                            summary += f"\n💰 Total: {total} MMK\n\n"
                            summary += "Type CONFIRM to confirm."

                            await send(token, chat_id, summary)
                        else:
                            await send(token, chat_id, res.get("reply_text"))

                    await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", task['id'])

                except Exception as e:
                    print("Task Error:", e)
                    await conn.execute(
                        "UPDATE task_queue SET status='failed', last_error=$1 WHERE id=$2",
                        str(e), task['id']
                    )

        except Exception as e:
            print("Worker Loop Error:", e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(run_worker())
