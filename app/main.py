from fastapi import FastAPI, Request, HTTPException
from .database import get_db_pool, init_db
from .worker import run_worker
import hashlib, asyncio, os

app = FastAPI()

@app.on_event("startup")
async def start():
    pool = await get_db_pool()
    await init_db(pool)
    asyncio.create_task(run_worker())

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):

    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != os.getenv("TELEGRAM_SECRET_TOKEN"):
        raise HTTPException(403)

    data = await request.json()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        if not biz:
            return {"ok": False}
        b_id = biz['id']

        if "message" not in data:
            return {"ok": True}

        chat_id = str(data["message"]["chat"]["id"])
        text = data["message"].get("text","")

        h = hashlib.md5(f"{b_id}:{chat_id}:{text}".encode()).hexdigest()

        await conn.execute("""
        INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
        VALUES ($1,$2,$3,$4)
        ON CONFLICT DO NOTHING
        """, b_id, chat_id, text, h)

    return {"ok": True}
