import hashlib
import os
import asyncio
from fastapi import FastAPI, Request
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()

# ၁။ Startup မှာ Database 初始化 လုပ်ပြီး Worker ကိုပါ တစ်ခါတည်း Run မယ်
@app.on_event("startup")
async def startup_event():
    pool = await get_db_pool()
    await init_db(pool)
    
    # Worker ကို Background Task အနေနဲ့ Run ခိုင်းထားခြင်း
    # ဒါမှ uvicorn က Port ကို ပုံမှန်အတိုင်း Bind လုပ်နိုင်မှာပါ
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

# ၂။ Render Health Check အတွက် (405 Error မတက်အောင်)
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "SellMate AI Multi-tenant System is running",
        "version": "1.0.2"
    }

# ၃။ Telegram Webhook Endpoint
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    data = await request.json()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # ဆိုင်ရှိမရှိ စစ်ဆေးခြင်း
        biz = await conn.fetchrow(
            "SELECT id FROM businesses WHERE tg_bot_token=$1", token
        )

        if not biz:
            return {"ok": False, "error": "Business not found"}

        b_id = biz['id']

        # Message ပါမှသာ Task Queue ထဲထည့်ခြင်း
        if "message" not in data or "text" not in data["message"]:
            return {"ok": True}

        chat_id = str(data["message"]["chat"]["id"])
        text = data["message"]["text"]

        # Duplicate Request တွေကို ကာကွယ်ဖို့ Hash လုပ်ခြင်း
        h = hashlib.md5(f"{b_id}:{chat_id}:{text}".encode()).hexdigest()

        # Task Queue ထဲသို့ ထည့်သွင်းခြင်း
        await conn.execute("""
            INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (request_hash) DO NOTHING
        """, b_id, chat_id, text, h)

    return {"ok": True}
