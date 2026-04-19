import asyncio
import time
import logging
import httpx
import os
from .ai import ai_service
from .database import get_db_pool

logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_tg(chat_id, text):
    """Telegram ကို စာပြန်ပို့တဲ့ helper function"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram: {e}")

async def run_worker():
    MAX_RETRIES = 3
    BACKOFF = [5, 15, 45]
    
    # Pool အဆင်သင့်ဖြစ်အောင် အရင်စောင့်မယ်
    db_pool = None
    while db_pool is None:
        db_pool = await get_db_pool()
        if not db_pool:
            logger.info("⏳ Waiting for database pool initialization...")
            await asyncio.sleep(1)

    logger.info("✅ Worker thread is monitoring the queue...")

    while True:
        try:
            async with db_pool.acquire() as conn:
                # 1. CRASH RECOVERY: ၂ မိနစ်ကျော် Processing ဖြစ်နေတာတွေကို Pending ပြန်လုပ်မယ်
                await conn.execute("""
                    UPDATE task_queue SET status='pending' 
                    WHERE status='processing' AND updated_at < NOW() - INTERVAL '2 minutes'
                """)

                # 2. GET TASK: Atomic Lock သုံးပြီး ယူမယ်
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', updated_at=NOW()
                    WHERE id = (SELECT id FROM task_queue WHERE status='pending' 
                                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if not task:
                    await asyncio.sleep(2)
                    continue

                start_time = time.time()
                chat_id = task['chat_id']
                
                try:
                    # 3. AI Processing
                    res_json, model = await ai_service.get_order_json(task['user_text'])
                    
                    # 4. Logic to Send Telegram Message
                    # AI က ထွက်လာတဲ့ JSON ကို သေသေချာချာ စာသားအဖြစ် ပြောင်းပြီး ပို့မယ်
                    response_text = f"✅ အော်ဒါမှတ်သားပြီးပါပြီ!\n\n{res_json}"
                    await send_tg(chat_id, response_text)

                    # 5. Success
                    await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])
                    
                    # 6. Log for observability
                    duration = int((time.time() - start_time) * 1000)
                    # ai_logs table မရှိသေးရင် error တက်မှာစိုးလို့ 
                    # အောက်က line ကို comment ခေတ္တပိတ်ထားနိုင်ပါတယ်
                    # await conn.execute("INSERT INTO ai_logs (shop_id, model_used, status, response_time_ms) VALUES ($1,$2,$3,$4)", 
                    #                    task['shop_id'], model, 'SUCCESS', duration)

                except Exception as e:
                    attempts = task['attempts'] + 1
                    logger.error(f"❌ Task {task['id']} failed (Attempt {attempts}): {e}")
                    
                    if attempts >= MAX_RETRIES:
                        # Move to Dead Letter Queue (Insert logic based on your schema)
                        await conn.execute("""
                            UPDATE task_queue SET status='failed', last_error=$2 
                            WHERE id=$1
                        """, task['id'], str(e))
                        await send_tg(chat_id, "⚠️ တောင်းပန်ပါတယ်၊ အော်ဒါကို ဆောင်ရွက်ပေးလို့ မရဖြစ်နေပါတယ်။ ခဏနေမှ ပြန်စမ်းကြည့်ပေးပါ။")
                    else:
                        # Retry logic
                        await conn.execute("""
                            UPDATE task_queue SET status='pending', attempts=$2, last_error=$3 
                            WHERE id=$1
                        """, task['id'], attempts, str(e))
                        await asyncio.sleep(BACKOFF[attempts-1])

        except Exception as e:
            logger.error(f"⚠️ Worker Loop Critical Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_worker())
