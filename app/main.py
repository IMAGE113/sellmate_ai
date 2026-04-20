from fastapi import FastAPI, Request, HTTPException
from .database import get_db_pool, init_db
from .worker import run_worker
import hashlib, asyncio, os

# FastAPI instance ကို တည်ဆောက်ခြင်း (Render deploy လုပ်ဖို့ အရေးကြီးဆုံးအပိုင်း)
app = FastAPI()

@app.on_event("startup")
async def start():
    """
    Server စတက်တာနဲ့ Database ချိတ်မယ်၊ Table တွေဆောက်မယ်၊ 
    ပြီးရင် နောက်ကွယ်မှာ အလုပ်လုပ်မယ့် Worker ကိုပါ တန်း Run မယ်။
    """
    pool = await get_db_pool()
    await init_db(pool)
    # Background task အနေနဲ့ worker ကို run ခိုင်းထားခြင်း
    asyncio.create_task(run_worker())

@app.get("/")
async def root():
    return {"message": "SellMate AI Server is running!"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """
    Telegram ကပို့သမျှ စာတွေကို ဒီ Webhook ကနေ လက်ခံမယ်။
    Token ကိုကြည့်ပြီး ဘယ်ဆိုင်လဲဆိုတာ ခွဲခြားမယ်။
    """
    # 1. Security Check (WeLoveRandy ဖြစ်ရမယ်)
    expected_secret = os.getenv("TELEGRAM_SECRET_TOKEN")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != expected_secret:
        logger_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        print(f"Secret Token Mismatch: Got {logger_secret}")
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. လက်ခံရရှိတဲ့ Data ကိုယူမယ်
    data = await request.json()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # 3. Database ထဲမှာ ဒီ Bot Token ရှိမရှိ စစ်မယ်
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        if not biz:
            return {"ok": False, "error": "Business not found"}
        
        b_id = biz['id']

        # 4. Message data မပါရင် အကြောင်းပြန်စရာမလိုလို့ ကျော်မယ်
        if "message" not in data:
            return {"ok": True}

        chat_id = str(data["message"]["chat"]["id"])
        text = data["message"].get("text", "")

        # 5. Message တစ်ခုတည်း ခဏခဏ မဝင်အောင် Hash လုပ်မယ်
        h = hashlib.md5(f"{b_id}:{chat_id}:{text}".encode()).hexdigest()

        # 6. Task Queue Table ထဲကို ထည့်မယ် (Worker က ဒါကိုကြည့်ပြီး အလုပ်လုပ်မယ်)
        await conn.execute("""
            INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (request_hash) DO NOTHING
        """, b_id, chat_id, text, h)

    return {"ok": True}
