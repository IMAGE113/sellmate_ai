import hashlib
import os
import asyncio
from fastapi import FastAPI, Request
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()

# Global variable အနေနဲ့ pool ကို သိမ်းထားမယ်
db_pool = None

@app.on_event("startup")
async def startup_event():
    global db_pool
    db_pool = await get_db_pool() # Pool ကို တစ်ခါပဲ ဆောက်တယ်
    await init_db(db_pool) # Database Tables တွေကို startup မှာ initialize လုပ်မယ်
    
    # Worker ကို background task အနေနဲ့ run တယ်
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "SellMate AI",
        "mode": "multi-tenant"
    }

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    global db_pool
    if not db_pool:
        db_pool = await get_db_pool()

    data = await request.json()

    async with db_pool.acquire() as conn:
        # 1. Bot Token စစ်ဆေးခြင်း
        biz = await conn.fetchrow(
            "SELECT id FROM businesses WHERE tg_bot_token=$1", token
        )

        if not biz:
            return {"ok": False, "error": "Business not found"}

        b_id = biz['id']

        # 2. Message data ကို စနစ်တကျယူခြင်း
        message = data.get("message")
        if not message or "text" not in message:
            return {"ok": True}

        raw_chat_id = message["chat"]["id"]
        text = message["text"]
        
        # 3. Request Hash (Duplicate ပို့တာ ကာကွယ်ဖို့)
        h = hashlib.md5(f"{b_id}:{raw_chat_id}:{text}".encode()).hexdigest()

        # 4. Task Queue ထဲသို့ ထည့်သွင်းခြင်း (Type mismatch fix)
        try:
            # မင်းရဲ့ Database က Integer ဖြစ်ဖို့များတဲ့အတွက် chat_id ကို int ပြောင်းပြီး အရင်ကြိုးစားမယ်
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, int(raw_chat_id), text, h)
        except Exception:
            # အကယ်၍ error တက်ခဲ့ရင် chat_id ကို string အဖြစ် ပြောင်းပြီး fallback လုပ်မယ်
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, str(raw_chat_id), text, h)

    return {"ok": True}
