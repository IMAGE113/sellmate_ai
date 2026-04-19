import asyncio
import logging
import httpx
import os
import json
from .ai import ai_service
from .database import get_db_pool

logger = logging.getLogger(__name__)
TELEGRAM_BOT_TOKEN = os.getenv("DATABASE_URL") # မင်းရဲ့ Bot Token ကို သုံးပါ

async def send_tg(chat_id, text):
    url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            return True
        except Exception as e:
            logger.error(f"TG Send Error: {e}")
            return False

async def run_worker():
    await asyncio.sleep(8)
    pool = await get_db_pool(for_worker=True)
    logger.info("🤖 AI Order Agent is monitoring with Confirmation Step...")

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
                    user_text = task['user_text']

                    # ၁။ AI ဆီပို့ပြီး Customer ရဲ့ စာကို Analysis လုပ်မယ်
                    # ai_service.process_chat က database connection ပါ ယူသွားမယ် (Menu ဖတ်ဖို့)
                    ai_response = await ai_service.process_customer_chat(user_text, conn, chat_id)
                    
                    intent = ai_response.get("intent") # intent: 'info_gathering', 'confirm_order', 'save_to_db'
                    reply_text = ai_response.get("reply_text")

                    # ၂။ AI က အချက်အလက်တွေ စုံလို့ Confirm လုပ်ခိုင်းတဲ့ အခြေအနေ
                    if intent == "confirm_order":
                        order_summary = ai_response.get("order_summary")
                        formatted_text = (
                            f"<b>📋 Order အနှစ်ချုပ်ကို စစ်ဆေးပေးပါ</b>\n\n"
                            f"👤 အမည်: {order_summary['name']}\n"
                            f"📞 ဖုန်း: {order_summary['phone']}\n"
                            f"🏠 လိပ်စာ: {order_summary['address']}\n"
                            f"🛍️ မှာယူသည့်ပစ္စည်း: {order_summary['items_list']}\n"
                            f"💰 စုစုပေါင်း: {order_summary['total']} Ks\n"
                            f"💳 ငွေပေးချေမှု: {order_summary['payment_type']}\n\n"
                            f"<i>အချက်အလက်တွေ မှန်ကန်တယ်ဆိုရင် 'Confirm' လို့ ပြောပေးပါခင်ဗျာ။</i>"
                        )
                        await send_tg(chat_id, formatted_text)

                    # ၃။ Customer က Confirm လုပ်လိုက်လို့ Database ထဲ သိမ်းမယ့် အခြေအနေ
                    elif intent == "save_to_db":
                        data = ai_response.get("final_order_data")
                        await conn.execute("""
                            INSERT INTO orders (customer_name, phone_no, address, items, total_price, payment_type, status)
                            VALUES ($1, $2, $3, $4, $5, $6, 'PENDING')
                        """, data['name'], data['phone'], data['address'], json.dumps(data['items']), data['total'], data['payment'])
                        
                        await send_tg(chat_id, "✅ အော်ဒါကို အောင်မြင်စွာ တင်ပြီးပါပြီ။ Dashboard မှာ စစ်ဆေးနိုင်ပါတယ်။ ကျေးဇူးတင်ပါတယ်!")

                    # ၄။ ပုံမှန် မေးမြန်းနေဆဲ အခြေအနေ (ဥပမာ- လိပ်စာမေးတာ၊ ဖုန်းမေးတာ)
                    else:
                        await send_tg(chat_id, reply_text)

                    await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])

            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5)
