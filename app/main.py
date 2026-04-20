import hashlib, asyncio, os
from fastapi import FastAPI, Request, HTTPException
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()

@app.on_event("startup")
async def start():
    """
    Server စတက်တာနဲ့ Database ချိတ်မယ်၊ Table တွေဆောက်မယ်၊ 
    Background Worker ကို Run မယ်။
    """
    pool = await get_db_pool()
    await init_db(pool)
    # Background မှာ task တွေကို စောင့်ကြည့်မယ့် worker ကို run ထားမယ်
    asyncio.create_task(run_worker())

@app.get("/")
async def root():
    return {"message": "SellMate AI SaaS Server is running!"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """
    Telegram ဆီကလာတဲ့ message တွေကို လက်ခံပြီး task_queue ထဲ ထည့်ပေးမယ်။
    """
    
    # 1. Security Check
    expected_secret = os.getenv("TELEGRAM_SECRET_TOKEN")
    secret_received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    
    if secret_received != expected_secret:
        return {"ok": False, "message": "Unauthorized"}

    # 2. Get JSON Data
    data = await request.json()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # 3. Token နဲ့ ဆိုင်ကို ရှာမယ်
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        
        if not biz:
            return {"ok": False, "error": "Business not registered"}
        
        business_id = biz['id']

        # 4. Message ပါမပါ စစ်မယ်
        if "message" not in data or "text" not in data["message"]:
            return {"ok": True}

        # 🔥 အရေးကြီးဆုံးအချက် - chat_id ကို integer (ဂဏန်း) အဖြစ် ပြောင်းသိမ်းမယ်
        try:
            chat_id = int(data["message"]["chat"]["id"])
            text = data["message"].get("text", "")
        except (KeyError, ValueError):
            return {"ok": False, "error": "Invalid data format"}

        # 5. Duplicate မဖြစ်အောင် Hash လုပ်မယ်
        h = hashlib.md5(f"{business_id}:{chat_id}:{text}".encode()).hexdigest()

        # 6. Task Queue ထဲ ထည့်မယ်
        # user_text နဲ့ business_id column တွေကို သုံးထားပါတယ်
        try:
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, business_id, chat_id, text, h)
        except Exception as e:
            print(f"Database Insertion Error: {e}")
            return {"ok": False, "error": "Failed to queue task"}

    return {"ok": True}
