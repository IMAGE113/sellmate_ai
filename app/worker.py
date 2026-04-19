import asyncio
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
        except: return False

async def run_worker():
    await asyncio.sleep(8)
    pool = await get_db_pool(for_worker=True)
    logger.info("✅ Worker is monitoring the queue...")

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
                    try:
                        res_json, model = await ai_service.get_order_json(task['user_text'])
                        
                        # AI Response ထဲက Data တွေကို စာသားအဖြစ် ပြောင်းမယ်
                        order_info = res_json.get('order', {}) if res_json else None
                        
                        if order_info and order_info != "None":
                            items = order_info.get('items', [])
                            if items:
                                items_text = "\n".join([f"✨ {i.get('name')} - {i.get('quantity', 1)} ခု" for i in items])
                                reply = f"✅ အော်ဒါမှတ်သားပြီးပါပြီခင်ဗျာ!\n\nမှာယူထားသည်များ -\n{items_text}\n\nစုစုပေါင်း - {order_info.get('total', 0)} Ks\n\nခေတ္တစောင့်ဆိုင်းပေးပါဦး။"
                            else:
                                reply = "မင်္ဂလာပါ! Randy's Cafe က ကြိုဆိုပါတယ်။ ဘာများ မှာယူချင်ပါသလဲ ခင်ဗျာ?"
                        else:
                            reply = "မင်္ဂလာပါ! အော်ဒါမှာယူလိုပါက ပစ္စည်းအမည်နဲ့ အရေအတွက်ကို ပြောပေးပါခင်ဗျာ။"

                        if await send_tg(chat_id, reply):
                            await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])
                    except Exception as e:
                        logger.error(f"❌ Processing Error: {e}")
                        await conn.execute("UPDATE task_queue SET status='pending', attempts=attempts+1 WHERE id=$1", task['id'])

            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5)
