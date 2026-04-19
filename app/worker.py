import asyncio
import time
import logging
import httpx
import os
from .ai import ai_service
from .database import get_db_pool

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_tg(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram: {e}")
            return False

async def run_worker():
    # --- 🛠️ CRITICAL FIX: ခဏစောင့်ခိုင်းမယ် ---
    # Main thread က database initialization လုပ်တာ ပြီးတဲ့အထိ စောင့်ပေးဖို့ပါ
    logger.info("⏳ Worker waiting 5 seconds for database to be fully ready...")
    await asyncio.sleep(5) 
    
    MAX_RETRIES = 3
    BACKOFF = [5, 15, 45]
    
    db_pool = None
    while db_pool is None:
        db_pool = await get_db_pool()
        if not db_pool:
            await asyncio.sleep(1)

    logger.info("✅ Worker thread is monitoring the queue...")

    while True:
        try:
            # 💡 Acquire connection inside the loop only when needed
            async with db_pool.acquire() as conn:
                # Crash Recovery
                await conn.execute("""
                    UPDATE task_queue SET status='pending' 
                    WHERE status='processing' AND updated_at < NOW() - INTERVAL '2 minutes'
                """)

                # Get Task
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', updated_at=NOW()
                    WHERE id = (SELECT id FROM task_queue WHERE status='pending' 
                                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if not task:
                    await asyncio.sleep(3)
                    continue

                chat_id = task['chat_id']
                try:
                    res_json, model = await ai_service.get_order_json(task['user_text'])
                    reply_text = f"✅ အော်ဒါမှတ်သားပြီးပါပြီ!\n\n{res_json}"
                    
                    if await send_tg(chat_id, reply_text):
                        await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])
                    else:
                        raise Exception("Telegram delivery failed")

                except Exception as e:
                    attempts = task['attempts'] + 1
                    if attempts >= MAX_RETRIES:
                        await conn.execute("UPDATE task_queue SET status='failed', last_error=$2 WHERE id=$1", task['id'], str(e))
                    else:
                        await conn.execute("UPDATE task_queue SET status='pending', attempts=$2, last_error=$3 WHERE id=$1", task['id'], attempts, str(e))
                        await asyncio.sleep(BACKOFF[attempts-1])

        except Exception as e:
            # "Another operation in progress" ဖြစ်ခဲ့ရင်လည်း loop က ဆက်သွားနေရမယ်
            logger.error(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5)
