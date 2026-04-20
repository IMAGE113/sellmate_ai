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
    # ✅ SQL Manual Run စရာမလိုအောင် ဒီမှာ အော်တို Init လုပ်ပေးထားပါတယ်
    await init_db(pool)
    
    # ✅ Background မှာ task တွေကို စောင့်ကြည့်မယ့် worker ကို run ထားမယ်
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

@app.get("/")
async def root():
    return {"message": "SellMate AI SaaS Server is running!"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """
    Telegram ဆီကလာတဲ့ message တွေကို လက်ခံပြီး task_queue ထဲ ထည့်ပေးမယ်။
    """
    
    # 1. Secret Token Check (Optional Safety)
    # မှတ်ချက် - Secret Token မသတ်မှတ်ရသေးရင် error မတက်အောင် skip လုပ်ထားပေးမယ်
    expected_secret = os.getenv("TELEGRAM_SECRET_TOKEN")
    secret_received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    
    if expected_secret and secret_received != expected_secret:
        return {"ok": False, "message": "Unauthorized"}

    # 2. Get JSON Data
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

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

        try:
            chat_id = int(data["message"]["chat"]["id"])
            text = data["message"].get("text", "")
        except (KeyError, ValueError):
            return {"ok": False, "error": "Invalid chat data"}

        # 5. Duplicate Task ကို တားဆီးရန် Hash လုပ်မယ်
        # (စာတစ်ကြောင်းတည်း ခဏခဏ ဝင်လာရင် task_queue ထဲ တစ်ခုပဲ ဝင်အောင်)
        h = hashlib.md5(f"{business_id}:{chat_id}:{text}".encode()).hexdigest()

        # 6. Task Queue ထဲ ထည့်မယ်
        try:
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, business_id, chat_id, text, h)
        except Exception as e:
            print(f"⚠️ Database Insertion Error: {e}")
            return {"ok": False, "error": "Failed to queue task"}

    return {"ok": True}
