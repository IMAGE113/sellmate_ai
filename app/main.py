import os
import json
import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from .database import get_db_pool, init_db
from .ai import parse_order
from .auth import generate_api_key

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_tg(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "SellMate AI Running"}

@app.post("/webhook/telegram")
async def webhook(req: Request):
    data = await req.json()
    msg = data.get("message", {})
    text = msg.get("text", "")
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if not text: return {"ok": True}

    async with app.state.pool.acquire() as conn:
        # 1. Shop Registration Flow
        if text.startswith("/start"):
            shop_name = text.replace("/start", "").strip() or "Randy's Cafe"
            key = generate_api_key()
            
            # Chat ID တူတာ ရှိမရှိ စစ်မယ်
            existing = await conn.fetchrow("SELECT api_key FROM businesses WHERE admin_chat_id = $1", chat_id)
            
            if not existing:
                await conn.execute(
                    "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3)",
                    shop_name, key, chat_id
                )
                await send_tg(chat_id, f"✅ {shop_name} Registered!\n\nYour API Key: `{key}`\n(Keep this for your Dashboard login!)")
            else:
                await send_tg(chat_id, f"You are already registered.\nYour API Key: `{existing['api_key']}`")
            return {"ok": True}

        # 2. AI Order Parsing Logic
        ai = parse_order(text)
        
        if ai["intent"] == "order":
            # ဘယ်ဆိုင်အတွက်လဲဆိုတာ chat_id နဲ့ ရှာမယ်
            business = await conn.fetchrow("SELECT id FROM businesses WHERE admin_chat_id = $1", chat_id)
            
            if business:
                bid = business['id']
                await conn.execute(
                    "INSERT INTO orders (business_id, items, total, status) VALUES ($1, $2, $3, $4)",
                    bid, json.dumps(ai["items"]), 0, "PENDING"
                )
                await send_tg(chat_id, f"🛒 အော်ဒါလက်ခံရရှိပါပြီ- {ai['items']}")
            else:
                await send_tg(chat_id, "ကျေးဇူးပြု၍ /start [ဆိုင်နာမည်] အရင်ရိုက်ပေးပါ။")
        else:
            await send_tg(chat_id, "မင်္ဂလာပါရှင်၊ ဘာမှာယူချင်ပါသလဲ?")

    return {"ok": True}
