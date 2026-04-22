import hashlib
import os
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()

# Global variable အနေနဲ့ pool ကို သိမ်းထားမယ် (ခဏခဏ get_db_pool ခေါ်စရာမလိုအောင်)
db_pool = None

@app.on_event("startup")
async def startup_event():
    global db_pool
    db_pool = await get_db_pool() # Pool ကို တစ်ခါပဲ ဆောက်တယ်
    await init_db(db_pool)
    
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
    # Pool မရှိသေးရင် (သို့) ချိတ်ဆက်မှုပြတ်နေရင် ပြန်ယူမယ်
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

        chat_id = message["chat"]["id"]
        text = message["text"]
        
        # 3. Request Hash (Duplicate ပို့တာ ကာကွယ်ဖို့)
        # CTO Tip: Timestamp ထည့်လိုက်ရင် ဝယ်သူက "Hi" နှစ်ခါရိုက်ရင် နှစ်ခါလုံး အလုပ်လုပ်မယ်
        h = hashlib.md5(f"{b_id}:{chat_id}:{text}".encode()).hexdigest()

        # 4. Task Queue ထဲသို့ ထည့်သွင်းခြင်း
        try:
            # chat_id ကို string အဖြစ်သိမ်းတာ ပိုစိတ်ချရတယ် (DB TEXT format ဖြစ်ရင်)
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, str(chat_id), text, h)
        except Exception as e:
            print(f"❌ Webhook DB Error: {e}")
            # Fallback for Integer chat_id
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, int(chat_id), text, h)

    return {"ok": True}
