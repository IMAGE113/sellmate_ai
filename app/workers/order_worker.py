import asyncio, json
from app.db.database import get_db_pool
from app.services.ai import ai
from app.services.telegram import send

async def run_worker():
    pool = await get_db_pool()

    while True:
        async with pool.acquire() as conn:
            task = await conn.fetchrow("""
            UPDATE task_queue SET status='processing'
            WHERE id = (
                SELECT id FROM task_queue WHERE status='pending'
                LIMIT 1 FOR UPDATE SKIP LOCKED
            ) RETURNING *
            """)

            if not task:
                await asyncio.sleep(1)
                continue

            biz = await conn.fetchrow("SELECT * FROM businesses WHERE id=$1", task["business_id"])
            menu = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", task["business_id"])

            pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2",
                                         task["chat_id"], task["business_id"])

            current = json.loads(pending["order_data"]) if pending else {"items":[]}

            res = await ai.process(task["user_text"], biz["name"], [dict(m) for m in menu], current)

            await conn.execute("""
            INSERT INTO pending_orders (chat_id,business_id,order_data)
            VALUES ($1,$2,$3)
            ON CONFLICT (chat_id,business_id)
            DO UPDATE SET order_data=$3
            """, task["chat_id"], task["business_id"], json.dumps(res["final_order_data"]))

            markup = None
            if res.get("ui") == "confirm_buttons":
                markup = {
                    "inline_keyboard":[[
                        {"text":"✅ Confirm","callback_data":"confirm"},
                        {"text":"🔄 Restart","callback_data":"restart"}
                    ]]
                }

            await send(biz["tg_bot_token"], task["chat_id"], res["reply_text"], markup)

            await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])
