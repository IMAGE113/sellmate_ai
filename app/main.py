import hashlib
import os
import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# ကိုယ့်ရဲ့ database နဲ့ worker ဖိုင်တွေထဲက function တွေကို import လုပ်မယ်
from .database import get_db_pool 
from .worker import run_worker

# Logging setup (Production မှာ log တွေကြည့်လို့ရအောင်)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- 🛠️ Background Worker Thread Runner (Free Plan အတွက်) ---
def start_worker_thread():
    """Worker ကို thread တစ်ခုအနေနဲ့ သီးသန့် loop တစ်ခုနဲ့ run ပေးမယ်"""
    logger.info("🧵 Starting Background Worker Thread...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_worker())
    except Exception as e:
        logger.error(f"❌ Worker Thread Crash: {e}")

# --- 🚀 Lifespan Manager (Startup & Shutdown Logic) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ၁။ Startup: Database Connection Pool တည်ဆောက်ပြီး Table တွေပါစစ်မယ်
    try:
        app.state.pool = await get_db_pool()
        logger.info("✅ Database System Initialized (Pool & Tables).")
    except Exception as e:
        logger.error(f"❌ critical: Database Initialization Failed: {e}")
        raise e

    # ၂။ Startup: Worker ကို Thread နဲ့ စတင်မယ်
    # daemon=True ထားတာက Web Server ပိတ်ရင် worker ပါ တစ်ခါတည်း သေသွားအောင်လို့ပါ
    worker_thread = threading.Thread(target=start_worker_thread, daemon=True)
    worker_thread.start()
    logger.info("✅ Hybrid Mode: Worker thread is running alongside Web Service.")

    yield
    
    # ၃။ Shutdown: Database connection တွေကို စနစ်တကျ ပြန်ပိတ်မယ်
    if hasattr(app.state, "pool") and app.state.pool:
        await app.state.pool.close()
        logger.info("🛑 Database pool closed. System shut down safely.")

# --- 🌐 FastAPI Instance ---
app = FastAPI(
    title="SellMate AI SaaS",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "SellMate AI Hybrid Core",
        "version": "2.5.1"
    }

# --- 🤖 Telegram Webhook Endpoint ---
@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
    except Exception:
        return {"ok": False, "detail": "Invalid JSON data"}

    # Telegram Data Extraction
    msg = data.get("message", {})
    text = msg.get("text")
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    # စာသားမပါရင် ဘာမှမလုပ်ဘဲ ပြန်ထွက်မယ်
    if not text or not chat_id:
        return {"ok": True}

    # IDEMPOTENCY: Duplicate Message တွေကို ကာကွယ်ဖို့ Hash လုပ်မယ်
    req_hash = hashlib.md5(f"{chat_id}:{message_id}".encode()).hexdigest()

    # Database ထဲကို Task အဖြစ် ထည့်သွင်းခြင်း
    async with app.state.pool.acquire() as conn:
        try:
            # task_queue table ထဲကို 'pending' status နဲ့ ထည့်မယ်
            # shop_id=1 က database.py မှာ အလိုအလျောက် ဆောက်ပေးထားတဲ့ ID ဖြစ်တယ်
            await conn.execute(
                """
                INSERT INTO task_queue (shop_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
                """,
                1, str(chat_id), text, req_hash
            )
            logger.info(f"📥 New Task Queued | Chat ID: {chat_id} | Hash: {req_hash}")
        except Exception as e:
            logger.error(f"❌ Queueing Error: {e}")
            return {"ok": False, "error": "Database insert failed"}

    # Telegram ကို ၂၀၀ မီလီစက္ကန့်အတွင်း OK ပြန်ရမယ် (ဒါမှ message ထပ်မပို့မှာ)
    return {"ok": True}
