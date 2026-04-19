import asyncio
import logging
import httpx
import os
import json
from .ai import ai_service
from .database import get_db_pool

logger = logging.getLogger(__name__)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_tg(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": chat_id, "text": text})
            return True
        except: return False

async def handle_db_operations(conn, ai_request):
    """AI က ခိုင်းတဲ့ database အလုပ်တွေကို လုပ်ပေးမယ့် function"""
    action = ai_request.get("action")
    
    if action == "get_menu":
        rows = await conn.fetch("SELECT name, price, stock FROM products WHERE is_available = TRUE")
        return [dict(r) for r in rows]
    
    elif action == "create_order":
        data = ai_request.get("order_data")
        await conn.execute("""
            INSERT INTO orders (customer_name, phone_no, address, items, total_price, payment_type)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, data['name'], data['phone'], data['address'], json.dumps(data['items']), data['total'], data['payment'])
        return "Order Successfully Saved to Database"
    
    return None

async def run_worker():
    await asyncio.sleep(8)
    pool = await get_db_pool(for_worker=True)
    logger.info("🤖 AI Agent Worker is ready to handle orders...")

    while True:
        try:
            async with pool.acquire() as conn:
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', updated_at=NOW()
                    WHERE id = (SELECT id FROM task_queue WHERE status='pending' 
                                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if task:
                    chat_id = task['chat_id']
                    # AI ကနေ database ခေါ်ဖို့ လိုမလို စစ်မယ်
                    res_json, model = await ai_service.process_customer_chat(task['user_text'], conn)
                    
                    # AI က စာပြန်ခိုင်းတာကို ပို့မယ်
                    reply_text = res_json.get("reply_to_user", "မင်္ဂလာပါ၊ ဘာကူညီပေးရမလဲခင်ဗျာ။")
                    if await send_tg(chat_id, reply_text):
                        await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])

            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"⚠️ Worker Error: {e}")
            await asyncio.sleep(5)
