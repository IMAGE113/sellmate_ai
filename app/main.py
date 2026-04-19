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

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    msg = data.get("message", {})
    text = msg.get("text", "")
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if not text: return {"ok": True}

    async with app.state.pool.acquire() as conn:
        # 1. Start Command - Shop Registration
        if text.startswith("/start"):
            shop_name = text.replace("/start", "").strip() or "New Shop"
            key = generate_api_key()
            await conn.execute(
                "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3)",
                shop_name, key, chat_id
            )
            await send_tg(chat_id, f"✅ {shop_name} Registered!\nAPI KEY: `{key}`")
            return {"ok": True}

        # 2. AI Order Parsing
        ai = parse_order(text)
        
        if ai["intent"] == "order":
            # POS Logic: Save to DB
            await conn.execute(
                "INSERT INTO orders (items, total, status) VALUES ($1, $2, $3)",
                json.dumps(ai["items"]), 0, "PENDING"
            )
            await send_tg(chat_id, f"🛒 အော်ဒါမှတ်သားပြီးပါပြီ- {ai['items']}")
        else:
            await send_tg(chat_id, "မင်္ဂလာပါ! ဘာကူညီပေးရမလဲရှင်?")

    return {"ok": True}
