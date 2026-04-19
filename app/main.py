import hashlib
import os
import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# ကိုယ့်ရဲ့ database နဲ့ worker ဖိုင်တွေထဲက function တွေကို import လုပ်မယ်
from .database import get_db_pool 
from .worker import run_worker  # worker.py ထဲမှာ run_worker() ဆိုတဲ့ function ရှိရမယ်

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 🛠️ Background Worker Thread Runner ---
def start_worker_thread():
    """Worker ကို thread တစ်ခုအနေနဲ့ သီးသန့် run ပေးမယ့် function"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_worker())
    except Exception as e:
        logger.error(f"❌ Worker Thread Error: {e}")

# --- 🚀 Lifespan Manager (Startup & Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ၁။ Database Connection Pool တည်ဆောက်မယ်
    try:
        app.state.pool = await get_db_pool()
        logger.info("✅ Database pool created.")
    except Exception as e:
        logger.error(f"❌ DB Pool Error: {e}")
        raise e

    # ၂။ Background Worker ကို Thread နဲ့ စတင်မယ် (FREE PLAN HACK)
    worker_thread = threading.Thread(target=start_worker_thread, daemon=True)
    worker_thread.start()
    logger.info("✅ Background Worker started in thread.")

    yield
    
    # ၃။ ပိတ်သိမ်းခြင်း
    if hasattr(app.state, "pool"):
        await app.state.pool.close()
        logger.info("🛑 DB Pool closed.")

# --- 🌐 FastAPI Instance ---
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "SellMate AI Hybrid Core is Running"}

@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
    except:
        return {"ok": False}

    msg = data.get("message", {})
    text = msg.get("text")
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    if not text or not chat_id:
        return {"ok": True}

    # IDEMPOTENCY: Request ထပ်မလာအောင် hash လုပ်မယ်
    req_hash = hashlib.md5(f"{chat_id}:{message_id}".encode()).hexdigest()

    async with app.state.pool.acquire() as conn:
        try:
            # Task ကို database queue ထဲ ထည့်လိုက်မယ်
            await conn.execute(
                """
                INSERT INTO task_queue (shop_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
                """,
                1, str(chat_id), text, req_hash
            )
            logger.info(f"📥 Task queued: {chat_id}")
        except Exception as e:
            logger.error(f"❌ DB Insert Error: {e}")

    return {"ok": True}
