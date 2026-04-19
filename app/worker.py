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
    """Telegram ကို စာပြန်ပို့တဲ့ Helper Function"""
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
    MAX_RETRIES = 3
    BACKOFF = [5, 15, 45]
    
    # ၁။ Database Pool ကို ရယူမယ် (Main.py က ဆောက်ပြီးသားကို စောင့်မယ်)
    db_pool = None
    while db_pool is None:
        db_pool = await get_db_pool()
        if not db_pool:
            logger.info("⏳ Worker waiting for database pool...")
            await asyncio.sleep(1)

    logger.info("✅ Worker thread is monitoring the queue...")

    while True:
        try:
            async with db_pool.acquire() as conn:
                # ၂။ Crash Recovery: ၂ မိနစ်ကျော်ကြာနေတဲ့ task တွေကို pending ပြန်လုပ်မယ်
                await conn.execute("""
                    UPDATE task_queue SET status='pending' 
                    WHERE status='processing' AND updated_at < NOW() - INTERVAL '2 minutes'
                """)

                # ၃။ Get Task: Atomic Lock သုံးပြီး Task တစ်ခုယူမယ်
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing', updated_at=NOW()
                    WHERE id = (SELECT id FROM task_queue WHERE status='pending' 
                                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if not task:
                    await asyncio.sleep(2) # အလုပ်မရှိရင် ၂ စက္ကန့်နားမယ်
                    continue

                start_time = time.time()
                chat_id = task['chat_id']
                logger.info(f"🤖 Processing task ID: {task['id']} for {chat_id}")
                
                try:
                    # ၄။ AI Processing
                    # ai_service ကနေ JSON response နဲ့ model name ကို ယူမယ်
                    res_json, model = await ai_service.get_order_json(task['user_text'])
                    
                    # ၅။ Telegram ဆီ စာပြန်ပို့မယ်
                    # res_json ထဲက data တွေကို သုံးပြီး စာသားလှလှလေး ပြင်ပို့လို့ရတယ်
                    reply_text = f"✅ အော်ဒါမှတ်သားပြီးပါပြီ!\n\n{res_json}"
                    success = await send_tg(chat_id, reply_text)

                    if success:
                        # ၆။ အောင်မြင်ရင် Status ကို completed ပြောင်းမယ်
                        await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])
                        logger.info(f"✅ Task {task['id']} completed successfully.")
                    else:
                        raise Exception("Telegram API failed to send message")

                except Exception as e:
                    attempts = task['attempts'] + 1
                    logger.error(f"❌ Task {task['id']} failed (Attempt {attempts}): {e}")
                    
                    if attempts >= MAX_RETRIES:
                        # Retry ကုန်သွားရင် status ကို failed ပြောင်းပြီး အကြောင်းပြချက်သိမ်းမယ်
                        await conn.execute("""
                            UPDATE task_queue SET status='failed', last_error=$2 
                            WHERE id=$1
                        """, task['id'], str(e))
                        await send_tg(chat_id, "⚠️ တောင်းပန်ပါတယ်၊ အော်ဒါကို ဆောင်ရွက်ပေးလို့ မရဖြစ်နေပါတယ်။ ဆိုင်ကို တိုက်ရိုက်ဆက်သွယ်ပေးပါ။")
                    else:
                        # Backoff နဲ့ Retry လုပ်မယ်
                        await conn.execute("""
                            UPDATE task_queue SET status='pending', attempts=$2, last_error=$3 
                            WHERE id=$1
                        """, task['id'], attempts, str(e))
                        await asyncio.sleep(BACKOFF[attempts-1])

        except Exception as e:
            logger.error(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5) # Critical error ဖြစ်ရင် ၅ စက္ကန့်နားမယ်
