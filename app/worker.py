import asyncio
import json
import logging
import httpx
import os
from .ai import ai_service
from .database import get_db_pool

logger = logging.getLogger(__name__)

async def send_tg(chat_id, text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            return True
        except: return False

async def run_worker():
    await asyncio.sleep(8)
    pool = await get_db_pool(for_worker=True)
    logger.info("🌐 Worker is monitoring SaaS queue...")

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
                    biz_id, chat_id, user_text = task['business_id'], task['chat_id'], task['user_text']

                    # ၁။ ဆိုင်အလိုက် Menu နှင့် နာမည်ကို ယူမယ်
                    shop = await conn.fetchrow("SELECT shop_name FROM businesses WHERE id=$1", biz_id)
                    products = await conn.fetch("SELECT name, price, stock FROM products WHERE business_id=$1 AND is_available=TRUE", biz_id)
                    
                    # ၂။ AI ဆီပို့မယ် (Context အဖြစ် ဆိုင်နာမည်နှင့် Menu ပါထည့်ပေးမယ်)
                    ai_res = await ai_service.process_chat(
                        user_text=user_text,
                        chat_id=chat_id,
                        shop_name=shop['shop_name'],
                        menu=[dict(p) for p in products]
                    )

                    intent = ai_res.get("intent")
                    
                    # ၃။ Logic ခွဲခြားခြင်း
                    if intent == "confirm_order":
                        summary = ai_res.get("order_summary")
                        text = (f"<b>📋 {shop['shop_name']} - Order အတည်ပြုရန်</b>\n\n"
                                f"👤 အမည်: {summary['name']}\n📞 ဖုန်း: {summary['phone']}\n"
                                f"🏠 လိပ်စာ: {summary['address']}\n🛍️ ပစ္စည်း: {summary['items_text']}\n"
                                f"💰 စုစုပေါင်း: {summary['total']} Ks\n\n"
                                f"မှန်ကန်ပါက 'Confirm' ဟု ပြောပေးပါခင်ဗျာ။")
                        await send_tg(chat_id, text)

                    elif intent == "save_to_db":
                        data = ai_res.get("final_order_data")
                        await conn.execute("""
                            INSERT INTO orders (business_id, customer_name, phone_no, address, items, total_price, payment_type)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """, biz_id, data['name'], data['phone'], data['address'], json.dumps(data['items']), data['total'], data['payment'])
                        await send_tg(chat_id, "✅ အော်ဒါတင်ပြီးပါပြီ။ ကျေးဇူးတင်ပါတယ်!")

                    else:
                        await send_tg(chat_id, ai_res.get("reply_text"))

                    await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])

            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Worker Error: {e}")
            await asyncio.sleep(5)
