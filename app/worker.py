import asyncio, json, logging, os, httpx
from .ai import ai_service
from .database import get_db_pool

async def send_tg(chat_id, text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

async def run_worker():
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
                    
                    shop = await conn.fetchrow("SELECT shop_name FROM businesses WHERE id=$1", biz_id)
                    products_raw = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", biz_id)
                    
                    # Error Fixed: ပိုမှန်ကန်သော list conversion
                    menu_list = [{"name": p['name'], "price": p['price']} for p in products_raw]
                    
                    ai_res = await ai_service.process_chat(user_text, chat_id, shop['shop_name'], menu_list)
                    intent = ai_res.get("intent")

                    if intent == "confirm_order":
                        s = ai_res.get("order_summary")
                        msg = (f"<b>📝 အော်ဒါအတည်ပြုပေးပါ</b>\n\n"
                               f"👤 အမည်: {s['name']}\n📞 ဖုန်း: {s['phone']}\n📍 လိပ်စာ: {s['address']}\n"
                               f"🛍️ မှာယူသည်: {s['items_text']}\n\n"
                               f"အချက်အလက်မှန်ကန်ပါက <b>'Confirm'</b> ဟု ပြောပေးပါခင်ဗျာ။")
                        await send_tg(chat_id, msg)
                    
                    elif intent == "save_to_db":
                        d = ai_res.get("final_order_data")
                        await conn.execute("""
                            INSERT INTO orders (business_id, customer_name, phone_no, address, items, total_price)
                            VALUES ($1, $2, $3, $4, $5, $6)
                        """, biz_id, d['name'], d['phone'], d['address'], json.dumps(d['items']), d['total'])
                        await send_tg(chat_id, "✅ အော်ဒါတင်ခြင်း အောင်မြင်ပါသည်။ ကျေးဇူးတင်ပါတယ်!")
                    
                    else:
                        await send_tg(chat_id, ai_res.get("reply_text"))

                    await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])

            await asyncio.sleep(2)
        except Exception as e:
            logging.error(f"Worker Error: {e}")
            await asyncio.sleep(5)
