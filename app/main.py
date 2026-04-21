import hashlib
import os
import asyncio
from fastapi import FastAPI, Request
from .database import get_db_pool, init_db
from .worker import run_worker

# 1. FastAPI instance ကို တည်ဆောက်ခြင်း (Uvicorn က ဒါကို ရှာမှာပါ)
app = FastAPI()

# 2. Startup Event: Database link ချိတ်ဆက်ပြီး Worker ကို Background မှာ run ခိုင်းခြင်း
@app.on_event("startup")
async def startup_event():
    pool = await get_db_pool()
    await init_db(pool)
    
    # Worker ကို background task အနေနဲ့ run မယ်
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

# 3. Root Endpoint: Render Health Check အတွက် (200 OK ပြန်ပေးဖို့)
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "SellMate AI",
        "mode": "multi-tenant"
    }

# 4. Telegram Webhook Endpoint
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    data = await request.json()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # Bot Token နဲ့ ဆိုင်ရှိမရှိ စစ်ဆေးခြင်း
        biz = await conn.fetchrow(
            "SELECT id FROM businesses WHERE tg_bot_token=$1", token
        )

        if not biz:
            return {"ok": False, "error": "Business not found"}

        b_id = biz['id']

        # Message မပါရင် ဘာမှမလုပ်ဘဲ ကျော်သွားမယ်
        if "message" not in data or "text" not in data["message"]:
            return {"ok": True}

        # Chat ID နဲ့ User ရိုက်လိုက်တဲ့ စာကို ယူခြင်း
        raw_chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]
        
        # Chat ID ကို String ပြောင်းခြင်း (Database TEXT Type နဲ့ ကိုက်ညီအောင်)
        chat_id_str = str(raw_chat_id)

        # Request တွေ ထပ်မနေအောင် Hash လုပ်ခြင်း
        h = hashlib.md5(f"{b_id}:{chat_id_str}:{text}".encode()).hexdigest()

        # Task Queue ထဲသို့ ထည့်သွင်းခြင်း
        try:
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, chat_id_str, text, h)
        except Exception:
            # အကယ်၍ Table Column က Integer ဖြစ်နေခဲ့ရင် fallback အနေနဲ့ သုံးဖို့
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, int(raw_chat_id), text, h)

    return {"ok": True}
