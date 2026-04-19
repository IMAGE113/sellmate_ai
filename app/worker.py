import asyncio, json, logging, os, httpx
from .ai import ai_service
from .database import get_db_pool

async def send_tg(chat_id, text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

async def run_worker():
    await asyncio.sleep(5)
    pool = await get_db_pool(for_worker=True)
    
    while True:
        try:
            async with pool.acquire() as conn:
                task = await conn.fetchrow("""
                    UPDATE task_queue SET status='processing'
                    WHERE id = (SELECT id FROM task_queue WHERE status='pending' 
                                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING *
                """)

                if task:
                    biz_id, chat_id, user_text = task['business_id'], task['chat_id'], task['user_text']
                    
                    # ၁။ SaaS Data ဖတ်မယ်
                    shop = await conn.fetchrow("SELECT shop_name FROM businesses WHERE id=$1", biz_id)
                    products = await conn.fetch("SELECT name, price, stock FROM products WHERE business_id=$1 AND is_available=TRUE", biz_id)
                    
                    # ၂။ AI ဆီပို့မယ်
                    ai_res = await ai_service.process_chat(user_text, chat_id, shop['shop_name'], [dict(p) for p in products])
                    
                    intent = ai_res.get("intent")
                    
                    # ၃။ Confirmation & DB Logic
                    if intent == "confirm_order":
                        s = ai_res.get("order_summary")
                        confirm_text = (f"<b>📋 {shop['shop_name']} - အော်ဒါအနှစ်ချုပ်</b>\n\n"
                                      f"👤 အမည်: {s['name']}\n📞 ဖုန်း: {s['phone']}\n🏠 လိပ်စာ: {s['address']}\n"
                                      f"🛍️ ပစ္စည်း: {s['items_text']}\n💰 စုစုပေါင်း: {s['total']} Ks\n\n"
                                      f"အချက်အလက်မှန်ကန်လျှင် 'Confirm' ဟု ပြောပေးပါခင်ဗျာ။")
                        await send_tg(chat_id, confirm_text)

                    elif intent == "save_to_db":
                        d = ai_res.get("final_order_data")
                        await conn.execute("""
                            INSERT INTO orders (business_id, customer_name, phone_no, address, items, total_price, payment_type)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """, biz_id, d['name'], d['phone'], d['address'], json.dumps(d['items']), d['total'], d['payment'])
                        await send_tg(chat_id, "✅ အော်ဒါတင်ခြင်း အောင်မြင်ပါသည်။ ကျေးဇူးတင်ပါတယ်။")
                    
                    else:
                        await send_tg(chat_id, ai_res.get("reply_text"))

                    await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])

            await asyncio.sleep(2)
        except Exception as e:
            logging.error(f"Worker Error: {e}")
            await asyncio.sleep(5)
