import hashlib
import os
import asyncio
from fastapi import FastAPI, Request
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()
db_pool = None

@app.on_event("startup")
async def startup_event():
    global db_pool
    db_pool = await get_db_pool()
    await init_db(db_pool)
    
    # Worker ကို background မှာ run မယ်
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

@app.get("/")
async def root():
    return {"status": "online", "service": "SellMate AI"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    global db_pool
    if not db_pool:
        db_pool = await get_db_pool()

    data = await request.json()

    async with db_pool.acquire() as conn:
        biz = await conn.fetchrow(
            "SELECT id FROM businesses WHERE tg_bot_token=$1", token
        )

        if not biz:
            return {"ok": False, "error": "Business not found"}

        b_id = biz['id']
        message = data.get("message")
        if not message or "text" not in message:
            return {"ok": True}

        raw_chat_id = message["chat"]["id"]
        text = message["text"]
        
        # ✅ CTO FIX: Invalid format specifier error ကို ကာကွယ်ဖို့ 
        # f-string မသုံးဘဲ string concatenation (+) နဲ့ hash လုပ်မယ်
        raw_hash_input = str(b_id) + ":" + str(raw_chat_id) + ":" + str(text)
        h = hashlib.md5(raw_hash_input.encode()).hexdigest()

        try:
            # Database က Integer column ဖြစ်ခဲ့ရင်
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, int(raw_chat_id), text, h)
        except Exception:
            # Database က Text column ဖြစ်ခဲ့ရင် fallback
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, str(raw_chat_id), text, h)

    return {"ok": True}
