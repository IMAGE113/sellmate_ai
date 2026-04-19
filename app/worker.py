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
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, json={"chat_id": chat_id, "text": text})
            return res.status_code == 200
        except Exception as e:
            logger.error(f"❌ TG Send Error: {e}")
            return False

async def run_worker():
    # ၁။ စနစ်တစ်ခုလုံး တည်ငြိမ်အောင် ခေတ္တစောင့်မယ်
    await asyncio.sleep(8)
    
    # ၂။ Worker အတွက် သီးသန့် Pool ယူမယ်
    pool = await get_db_pool(for_worker=True)
    logger.info("✅ Worker monitoring queue with private pool...")

    while True:
        try:
            async with pool.acquire() as conn:
                # ၃။ Task တစ်ခုဆွဲယူမယ်
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', updated_at=NOW()
                    WHERE id = (SELECT id FROM task_queue WHERE status='pending' 
                                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if task:
                    chat_id = task['chat_id']
                    try:
                        # AI ဆီပို့မယ်
                        res_json, model = await ai_service.get_order_json(task['user_text'])
                        
                        # Telegram ဆီပို့မယ်
                        reply = f"✅ အော်ဒါအသေးစိတ်:\n{res_json}"
                        if await send_tg(chat_id, reply):
                            await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])
                            logger.info(f"✅ Completed Task {task['id']}")
                    except Exception as e:
                        logger.error(f"❌ Task Processing Error: {e}")
                        await conn.execute("UPDATE task_queue SET status='pending', attempts=attempts+1 WHERE id=$1", task['id'])

            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5)
