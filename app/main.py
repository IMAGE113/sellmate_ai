import os
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import httpx

from app.database import get_db_pool, init_db
from app.ai import parse_order
from app.auth import generate_api_key

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status":"running"}

# 👉 ADMIN REGISTER
@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()

    msg = data.get("message", {})
    text = msg.get("text")
    chat_id = str(msg.get("chat", {}).get("id"))

    if not text:
        return {"ok":True}

    # register shop
    if text.startswith("/start"):
        name = text.replace("/start","").strip()

        key = generate_api_key()

        async with app.state.pool.acquire() as conn:
            bid = await conn.fetchval(
                "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3) RETURNING id",
                name, key, chat_id
            )

        await send(chat_id, f"✅ {name} registered\nAPI KEY:\n{key}")
        return {"ok":True}

    # AI parse
    ai = parse_order(text)

    if ai["intent"] == "order":
        items = ai["items"]

        async with app.state.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (items, total) VALUES ($1,$2)",
                items, 0
            )

            admin = await conn.fetchrow(
                "SELECT admin_chat_id FROM businesses LIMIT 1"
            )

        await send(admin["admin_chat_id"], f"🛒 New Order: {items}")
        await send(chat_id, "✅ Order received")

    else:
        await send(chat_id, "ဘာမှာယူချင်ပါသလဲရှင်?")

    return {"ok":True}
