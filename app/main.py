import os
import json
import httpx
import logging
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from .database import get_db_pool, init_db
from .ai import parse_order
from .auth import generate_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_tg(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook/telegram")
async def webhook(req: Request):
    try:
        data = await req.json()
        msg = data.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        
        if not text: return {"ok": True}
        
        logger.info(f"TEXT RECEIVED: {text}")

        async with app.state.pool.acquire() as conn:
            # ၁။ /start နဲ့ ဆိုင် register လုပ်ခြင်း
            if text.startswith("/start"):
                shop_name = text.replace("/start", "").strip() or "My Shop"
                api_key = generate_api_key()
                await conn.execute(
                    "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3) ON CONFLICT (admin_chat_id) DO NOTHING",
                    shop_name, api_key, chat_id
                )
                await send_tg(chat_id, "✅ ဆိုင်မှတ်ပုံတင်ခြင်း အောင်မြင်ပါသည်။")
                return {"ok": True}

            # ၂။ AI နဲ့ စာသားကို ခွဲခြမ်းစိတ်ဖြာခြင်း
            ai_res = parse_order(text)
            business = await conn.fetchrow("SELECT id FROM businesses WHERE admin_chat_id = $1", chat_id)

            if not business:
                await send_tg(chat_id, "ကျေးဇူးပြု၍ `/start [ဆိုင်နာမည်]` အရင်လုပ်ပေးပါ။")
                return {"ok": True}

            # ၃။ Order ဖြစ်မဖြစ် စစ်ဆေးပြီး သိမ်းဆည်းခြင်း
            items = ai_res.get("items", [])
            if (ai_res.get("intent") == "order") and items:
                await conn.execute(
                    "INSERT INTO orders (business_id, items, status) VALUES ($1, $2, 'PENDING')",
                    business['id'], json.dumps(items)
                )
                summary = "\n".join([f"• {i['name']} - {i['qty']} ခု" for i in items])
                await send_tg(chat_id, f"🛒 *အော်ဒါလက်ခံရရှိပါပြီ!*\n\n{summary}\n\nDashboard မှာ စစ်ဆေးနိုင်ပါတယ်။")
                logger.info(f"DB SUCCESS: Order saved for Business {business['id']}")
            else:
                await send_tg(chat_id, "မင်္ဂလာပါရှင်၊ ဘာများ မှာယူချင်ပါသလဲ? (ဥပမာ- Coffee ၂ ခွက်ပေးပါ)")

    except Exception as e:
        logger.error(f"SYSTEM ERROR: {e}")
        
    return {"ok": True}
