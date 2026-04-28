import asyncio
import logging
import json # <--- JSON format ပြောင်းဖို့ ထည့်ထားတယ်
from app.db.database import get_db_pool
from app.services.ai import ai
from app.services.telegram import send

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def run_worker():
    pool = await get_db_pool()
    logging.info("🚀 SellMate AI Worker started and listening for tasks...")

    while True:
        try:
            async with pool.acquire() as conn:

                # 🔄 Task ကို Safe ဖြစ်အောင် ယူမယ်
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

                logging.info(f"📩 Processing task {task['id']} for Shop ID: {task['business_id']}")

                # 📦 ဆိုင်ရဲ့ အချက်အလက် (Token) ကို ယူမယ်
                biz = await conn.fetchrow(
                    "SELECT id, name, tg_bot_token FROM businesses WHERE id=$1",
                    task["business_id"]
                )

                if not biz:
                    logging.warning(f"⚠️ Business {task['business_id']} not found. Cleaning task.")
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])
                    continue

                # 📜 Menu ကို ယူမယ်
                menu_rows = await conn.fetch(
                    "SELECT name, price FROM products WHERE business_id=$1",
                    task["business_id"]
                )
                menu = [dict(m) for m in menu_rows]

                # 🧠 ယခင်မှာထားတဲ့ အချက်အလက် (Memory) ကို ယူမယ်
                pending = await conn.fetchrow(
                    "SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2",
                    task["chat_id"], task["business_id"]
                )

                # Database က JSONB ဆိုရင် dict အဖြစ်လာမယ်၊ TEXT ဆိုရင် string လာမယ်
                current = pending["order_data"] if pending else {"items": []}
                if isinstance(current, str):
                    current = json.loads(current)

                # 🤖 AI နဲ့ အဖြေထုတ်မယ်
                res = await ai.process(
                    task["user_text"],
                    biz["name"],
                    menu,
                    current
                )

                final_data = res.get("final_order_data", {})

                # 💾 Memory သိမ်းမယ် (Error မတက်အောင် json.dumps သုံးထားတယ်)
                # ဒါဆိုရင် Table column က TEXT ရော JSONB ပါ အဆင်ပြေပါတယ်
                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, business_id)
                DO UPDATE SET order_data=$3, updated_at=NOW()
                """, 
                task["chat_id"], 
                task["business_id"], 
                json.dumps(final_data)) # <--- ဒီနေရာက အဓိက အဖြေပါပဲ

                # 🎛 UI Buttons
                markup = None
                if res.get("ui") == "confirm_buttons":
                    markup = {
                        "inline_keyboard": [[
                            {"text": "✅ Confirm Order", "callback_data": "confirm"},
                            {"text": "🔄 Restart", "callback_data": "restart"}
                        ]]
                    }

                # 📤 Telegram ဆီ Reply ပြန်ပို့မယ်
                await send(
                    biz["tg_bot_token"],
                    task["chat_id"],
                    res.get("reply_text", "နားမလည်ပါဘူးခင်ဗျာ။"),
                    reply_markup=markup
                )

                # 🧹 Task ကို Queue ထဲက ဖျက်မယ်
                await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])
                logging.info(f"✅ Task {task['id']} completed successfully.")

        except Exception as e:
            logging.error(f"🔥 Worker Error: {str(e)}")
            await asyncio.sleep(2)

        await asyncio.sleep(0.1)
