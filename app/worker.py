import asyncio
import json
import httpx
import logging
from .database import get_db_pool
from .ai import ai

# Logging setup - Render Log မှာ အသေးစိတ်မြင်ရအောင် လုပ်ထားပါတယ်။
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client = httpx.AsyncClient(timeout=30.0)

async def send_telegram(token, chat_id, text):
    """Telegram API ဆီ စာသားလှမ်းပို့တဲ့ Function"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": str(chat_id), 
            "text": text, 
            "parse_mode": "HTML"
        }
        
        logger.info(f"📡 Sending to TG: {chat_id}")
        resp = await http_client.post(url, json=payload)
        result = resp.json()
        
        if not result.get("ok"):
            logger.error(f"❌ TG API Error: {result.get('description')}")
        else:
            logger.info(f"✅ TG Message Sent Successfully")
        return result
    except Exception as e:
        logger.error(f"❌ Telegram Network Error: {e}")

def validate_items(items, menu):
    """AI ဆီကရလာတဲ့ items တွေကို လက်ရှိ Menu နဲ့ တိုက်စစ်ပြီး ဈေးနှုန်းတွက်ချက်ခြင်း"""
    valid = []
    total = 0
    menu_dict = {m['name'].lower(): m['price'] for m in menu}
    
    if not items:
        return valid, total

    for i in items:
        name = str(i.get('name', '')).lower()
        if name in menu_dict:
            qty = max(1, int(i.get('qty', 1)))
            price = menu_dict[name]
            valid.append({"name": name, "qty": qty, "price": price})
            total += qty * price
    return valid, total

async def run_worker():
    pool = await get_db_pool()
    logger.info("🔥 Worker is active and listening...")

    while True:
        try:
            async with pool.acquire() as conn:
                # Pending ဖြစ်နေတဲ့ task တစ်ခုကို ဆွဲထုတ်မယ်
                task = await conn.fetchrow("""
                UPDATE task_queue SET status='processing'
                WHERE id = (
                    SELECT id FROM task_queue
                    WHERE status='pending'
                    ORDER BY id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, business_id, chat_id, user_text
                """)

                if not task:
                    await asyncio.sleep(2)
                    continue

                t_id = task['id']
                b_id = task['business_id']
                chat_id = task['chat_id']
                user_text = task['user_text']
                
                logger.info(f"📩 Processing Task {t_id} for Business {b_id}")

                # ဆိုင်အချက်အလက် ယူမယ်
                biz = await conn.fetchrow("SELECT tg_bot_token, shop_name FROM businesses WHERE id=$1", b_id)
                if not biz:
                    logger.error(f"🚫 Business {b_id} not found")
                    await conn.execute("UPDATE task_queue SET status='failed' WHERE id=$1", t_id)
                    continue

                token = biz['tg_bot_token']
                shop_name = biz['shop_name']
                
                # Menu (Products) ယူမယ်
                menu_rows = await conn.fetch("SELECT name, price FROM products WHERE business_id=$1", b_id)
                menu = [{"name": m["name"], "price": m["price"]} for m in menu_rows]
                
                # လက်ရှိ Order status (Pending Order) ယူမယ်
                pending = await conn.fetchrow("SELECT order_data FROM pending_orders WHERE chat_id=$1 AND business_id=$2", chat_id, b_id)
                current_order_json = pending['order_data'] if pending else "{}"

                # AI Processing - ဒီနေရာမှာ AI က အဖြေထုတ်ပေးတာပါ
                logger.info(f"🤖 AI is thinking for {chat_id}...")
                res = await ai.process(user_text, shop_name, menu, current_order_json)
                
                # AI အဖြေကို Log မှာ ပြမယ် (Debug လုပ်ရလွယ်အောင်)
                logger.info(f"🤖 AI Result: {json.dumps(res, ensure_ascii=False)}")

                # --- Error Fix: message text is empty ဖြစ်မှာစိုးလို့ စစ်ပေးခြင်း ---
                reply_text = res.get('reply_text')
                if not reply_text or str(reply_text).strip() == "":
                    reply_text = "တောင်းပန်ပါတယ်ခင်ဗျာ၊ ကျွန်တော် နားမလည်လိုက်လို့ တစ်ချက်လောက် ပြန်ပြောပေးပါဦး။"

                # Database Update (Pending Order သိမ်းမယ်)
                new_order_data = res.get('final_order_data', {})
                valid_items, total = validate_items(new_order_data.get('items', []), menu)
                new_order_data['items'] = valid_items
                new_order_data['total_price'] = total

                await conn.execute("""
                INSERT INTO pending_orders (chat_id, business_id, order_data)
                VALUES ($1,$2,$3)
                ON CONFLICT (chat_id,business_id)
                DO UPDATE SET order_data=$3, updated_at=NOW()
                """, chat_id, b_id, json.dumps(new_order_data))

                # Telegram ဆီ စာပြန်ပို့မယ်
                await send_telegram(token, chat_id, reply_text)

                # Task ပြီးဆုံးကြောင်း မှတ်သားမယ်
                await conn.execute("UPDATE task_queue SET status='done' WHERE id=$1", t_id)
                logger.info(f"🏁 Task {t_id} completed successfully.")

        except Exception as e:
            logger.error(f"⚠️ Worker Loop Error: {e}")
            await asyncio.sleep(5)
