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
    
    # Background Worker စတင်ခြင်း
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

@app.get("/")
async def root():
    return {
        "status": "online", 
        "service": "SellMate AI",
        "timestamp": os.getenv("RENDER_START_TIME", "active")
    }

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    global db_pool
    if not db_pool:
        db_pool = await get_db_pool()

    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    async with db_pool.acquire() as conn:
        # 1. BusinessBot စစ်ဆေးခြင်း
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        if not biz:
            return {"ok": False, "error": "Business not found"}

        b_id = biz['id']
        message = data.get("message") or data.get("edited_message")
        
        if not message or "text" not in message:
            return {"ok": True}

        raw_chat_id = message["chat"]["id"]
        text = message["text"]
        
        # ✅ CTO FIX: Concatenation သုံးပြီး hash လုပ်ခြင်း (f-string error ကာကွယ်ရန်)
        hash_input = str(b_id) + ":" + str(raw_chat_id) + ":" + str(text)
        h = hashlib.md5(hash_input.encode()).hexdigest()

        # ✅ Type Conversion: Database က BigInt ဖြစ်ဖို့များလို့ int အရင်ပြောင်းမယ်
        try:
            clean_chat_id = int(raw_chat_id)
        except (ValueError, TypeError):
            clean_chat_id = str(raw_chat_id)

        # 2. Task Queue ထဲသို့ ထည့်သွင်းခြင်း
        try:
            # ပထမအကြိမ်: Integer အဖြစ် စမ်းထည့်ခြင်း
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, clean_chat_id, text, h)
        except Exception:
            # ဒုတိယအကြိမ် (Fallback): String အဖြစ် စမ်းထည့်ခြင်း
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, str(raw_chat_id), text, h)

    return {"ok": True}
