import asyncio
import logging
from app.db.database import get_db_pool
from app.services.ai import ai
from app.services.telegram import send

logging.basicConfig(level=logging.INFO)

async def run_worker():
    pool = await get_db_pool()
    logging.info("🚀 Worker started...")

    while True:
        try:
            async with pool.acquire() as conn:

                # 🔄 Get task safely
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

                # 📦 Load business
                biz = await conn.fetchrow(
                    "SELECT id, name, tg_bot_token FROM businesses WHERE id=$1",
                    task["business_id"]
                )

                if not biz:
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])
                    continue

                # 📜 Load menu
                menu_rows = await conn.fetch(
                    "SELECT name, price FROM products WHERE business_id=$1",
                    task["business_id"]
                )
                menu = [dict(m) for m in menu_rows]

                # 🧠 Load previous order (JSONB → no json.loads)
                pending = await conn.fetchrow(
                    "SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2",
                    task["chat_id"], task["business_id"]
                )

                current = pending["order_data"] if pending else {"items": []}

                # 🤖 AI Processing
                res = await ai.process(
                    task["user_text"],
                    biz["name"],
                    menu,
                    current
                )

                final_data = res.get("final_order_data", {})

                # 💾 Save memory (JSONB → no json.dumps)
                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, business_id)
                DO UPDATE SET order_data=$3, updated_at=NOW()
                """, task["chat_id"], task["business_id"], final_data)

                # 🎛 UI Buttons
                markup = None
                if res.get("ui") == "confirm_buttons":
                    markup = {
                        "inline_keyboard": [[
                            {"text": "✅ Confirm", "callback_data": "confirm"},
                            {"text": "🔄 Restart", "callback_data": "restart"}
                        ]]
                    }

                # 📤 Send message
                await send(
                    biz["tg_bot_token"],
                    task["chat_id"],
                    res.get("reply_text", "နားမလည်ပါဘူးခင်ဗျာ။"),
                    reply_markup=markup
                )

                # 🧹 Cleanup task
                await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])

        except Exception as e:
            logging.error(f"🔥 Worker Error: {str(e)}")
            await asyncio.sleep(2)
