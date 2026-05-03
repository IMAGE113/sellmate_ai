import asyncio
import logging
import json
from app.db.database import get_db_pool
from app.services.ai import ai
from app.services.telegram import send

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
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])
                    continue

                # 📜 Menu ကို ယူမယ် (Price တွက်ဖို့ လိုတယ်)
                menu_rows = await conn.fetch(
                    "SELECT name, price FROM products WHERE business_id=$1",
                    task["business_id"]
                )
                menu = [dict(m) for m in menu_rows]

                # 🧠 Memory ယူမယ်
                pending = await conn.fetchrow(
                    "SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2",
                    task["chat_id"], task["business_id"]
                )

                current = pending["order_data"] if pending else {"items": []}
                if isinstance(current, str):
                    current = json.loads(current)

                # 🤖 AI နဲ့ အဖြေထုတ်မယ်
                res = await ai.process(task["user_text"], biz["name"], menu, current)
                final_data = res.get("final_order_data", {})

                # ⚡ အဓိကပြင်ဆင်ချက်: Intent 'confirmed' ဖြစ်သွားရင် Final Table ထဲပို့မယ်
                if res.get("intent") == "confirmed" and final_data.get("items"):
                    
                    # 1. Total Price တွက်ချက်ခြင်း
                    total_price = 0
                    for item in final_data["items"]:
                        price = next((m["price"] for m in menu if m["name"] == item["name"]), 0)
                        total_price += (price * item["qty"])

                    # 2. Orders Table ထဲသို့ သိမ်းဆည်းခြင်း
                    await conn.execute("""
                    INSERT INTO orders (
                        business_id, chat_id, customer_name, phone_no, 
                        address, payment_method, items, total_price
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, 
                    task["business_id"], task["chat_id"], final_data.get("customer_name"),
                    final_data.get("phone_no"), final_data.get("address"), 
                    final_data.get("payment_method"), json.dumps(final_data["items"]), total_price)

                    # 3. Pending Memory ကို ရှင်းထုတ်ခြင်း (အော်ဒါပြီးသွားပြီဖြစ်လို့)
                    await conn.execute(
                        "DELETE FROM pending_orders WHERE chat_id=$1 AND business_id=$2",
                        task["chat_id"], task["business_id"]
                    )
                    logging.info(f"✅ Order Confirmed and Saved for Chat ID: {task['chat_id']}")

                else:
                    # အော်ဒါမပြီးသေးရင် Memory ကို Update လုပ်ထားမယ်
                    await conn.execute("""
                    INSERT INTO pending_orders (chat_id, business_id, order_data)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (chat_id, business_id)
                    DO UPDATE SET order_data=$3, updated_at=NOW()
                    """, 
                    task["chat_id"], task["business_id"], json.dumps(final_data))

                # 🎛 UI Buttons logic
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

                # 🧹 Task Cleaning
                await conn.execute("DELETE FROM task_queue WHERE id=$1", task["id"])

        except Exception as e:
            logging.error(f"🔥 Worker Error: {str(e)}")
            await asyncio.sleep(2)

        await asyncio.sleep(0.1)
