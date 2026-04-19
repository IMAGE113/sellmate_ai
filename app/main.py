import hashlib
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from .database import get_db_pool  # database.py ထဲက get_db_pool ကို ခေါ်သုံးမယ်

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ၁။ Lifespan Manager (Startup & Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # App စတက်ချိန်မှာ Database Connection Pool ကို အရင်ဆောက်မယ်
    try:
        app.state.pool = await get_db_pool()
        logger.info("✅ Database connection pool created successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to create DB pool: {e}")
        raise e
        
    yield
    
    # App ပိတ်ချိန်မှာ Connection Pool ကို ပြန်ပိတ်မယ်
    if hasattr(app.state, "pool"):
        await app.state.pool.close()
        logger.info("🛑 Database connection pool closed.")

# --- ၂။ FastAPI Instance ---
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "SellMate AI SaaS is Running"}

# --- ၃။ Telegram Webhook Endpoint ---
@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    msg = data.get("message", {})
    text = msg.get("text")
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    # စာသားမပါရင် (ဥပမာ- sticker/photo) ဘာမှမလုပ်ဘူး
    if not text or not chat_id:
        return {"ok": True}

    # IDEMPOTENCY GUARD: Message ID နဲ့ Chat ID ကိုသုံးပြီး Hash လုပ်မယ်
    # ဒါမှ Telegram က request တစ်ခုတည်းကို ၂ ခါပို့ရင် duplicate order မဖြစ်မှာ
    req_hash = hashlib.md5(f"{chat_id}:{message_id}".encode()).hexdigest()

    # Database ထဲကို Task အနေနဲ့ ထည့်မယ်
    async with app.state.pool.acquire() as conn:
        try:
            # Task Queue ထဲကို pending status နဲ့ ထည့်လိုက်မယ်
            # shop_id ကို လောလောဆယ် ၁ လို့ပဲ သတ်မှတ်ထားတယ်
            await conn.execute(
                """
                INSERT INTO task_queue (shop_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
                """,
                1, str(chat_id), text, req_hash
            )
            logger.info(f"📥 New task queued from {chat_id}")
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            return {"ok": False, "error": str(e)}

    # Webhook ကို ၂၀၀ မီလီစက္ကန့်အတွင်း အမြန်ပြန်ဖြေရမယ်
    return {"ok": True}
