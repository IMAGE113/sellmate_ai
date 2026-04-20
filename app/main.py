import hashlib, asyncio, os
from fastapi import FastAPI, Request, HTTPException
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()

@app.on_event("startup")
async def start():
    """
    Server စတက်တာနဲ့ Database ချိတ်မယ်၊ Table တွေဆောက်မယ်၊ 
    နောက်ကွယ်က Worker ကိုပါ Run မယ်။
    """
    pool = await get_db_pool()
    # Table တွေ အလိုအလျောက် ဆောက်ပေးမယ့် function
    await init_db(pool)
    # Background မှာ AI process လုပ်မယ့် Worker ကို run ထားမယ်
    asyncio.create_task(run_worker())

@app.get("/")
async def root():
    return {"message": "SellMate AI SaaS Server is running!"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """
    Telegram Bot ဆီကဝင်လာသမျှ Message တွေကို လက်ခံပြီး 
    သက်ဆိုင်ရာ ဆိုင်အလိုက် ခွဲခြားသိမ်းဆည်းပေးမယ်။
    """
    
    # 1. Security Check (Render Environment မှာ သတ်မှတ်ထားတဲ့ Secret စစ်မယ်)
    expected_secret = os.getenv("TELEGRAM_SECRET_TOKEN")
    secret_received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    
    if secret_received != expected_secret:
        print(f"Unauthorized Access Attempt! Secret mismatch.")
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. လက်ခံရရှိတဲ့ JSON Data ကိုယူမယ်
    data = await request.json()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # 3. Database ထဲမှာ ဒီ Bot Token နဲ့ ဆိုင်ရှိမရှိ စစ်မယ်
        # (Database ထဲမှာ tg_bot_token ဆိုတဲ့ column ရှိနေရပါမယ်)
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        
        if not biz:
            print(f"Alert: Bot token {token} is not registered in our database!")
            return {"ok": False, "error": "Business not found"}
        
        business_id = biz['id']

        # 4. Message data မပါရင် ကျော်မယ် (ဥပမာ- Edited messages တွေဆိုရင်)
        if "message" not in data or "text" not in data["message"]:
            return {"ok": True}

        chat_id = str(data["message"]["chat"]["id"])
        text = data["message"].get("text", "")

        # 5. Message တစ်ခုတည်း ခဏခဏ Duplicate မဖြစ်အောင် Hash လုပ်မယ်
        h = hashlib.md5(f"{business_id}:{chat_id}:{text}".encode()).hexdigest()

        # 6. Task Queue ထဲကို သိမ်းမယ် (Worker က ဒါကိုကြည့်ပြီး AI နဲ့ ဆက်သွယ်ပေးမှာပါ)
        try:
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (request_hash) DO NOTHING
            """, business_id, chat_id, text, h)
        except Exception as e:
            print(f"Database Error: {e}")
            return {"ok": False, "error": "Queue insertion failed"}

    return {"ok": True}
