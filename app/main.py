import hashlib
import os
import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from .database import get_db_pool, init_db
from .worker import run_worker

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Worker Thread Launcher ---
def start_worker_thread():
    """Worker ကို Thread သီးသန့်နဲ့ Run ပေးမယ်"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_worker())
    except Exception as e:
        logger.error(f"❌ Worker Thread Crash: {e}")

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ၁။ Startup: Database Pool ဆောက်မယ်
    app.state.pool = await get_db_pool()
    
    # ၂။ Startup: Table Initialization (အလုပ်ပြီးအောင် အရင်စောင့်မယ်)
    # ဒါမှ 'operation in progress' error မတက်မှာပါ
    await init_db(app.state.pool)
    
    # ၃။ Startup: အားလုံးအဆင်သင့်ဖြစ်ပြီဆိုမှ Worker ကို Thread နဲ့ စတင်မယ်
    worker_thread = threading.Thread(target=start_worker_thread, daemon=True)
    worker_thread.start()
    logger.info("🚀 System is fully online: Webhook & Worker are active.")

    yield
    
    # ၄။ Shutdown: Pool ပြန်ပိတ်မယ်
    if hasattr(app.state, "pool"):
        await app.state.pool.close()
        logger.info("🛑 Database pool closed.")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "running", "mode": "hybrid-worker"}

@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        msg = data.get("message", {})
        text = msg.get("text")
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")

        if not text or not chat_id: return {"ok": True}

        # Duplicate message စစ်ဖို့ hash လုပ်မယ်
        req_hash = hashlib.md5(f"{chat_id}:{message_id}".encode()).hexdigest()

        async with app.state.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_queue (shop_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
                """,
                1, str(chat_id), text, req_hash
            )
            logger.info(f"📥 New Task Queued for Chat ID: {chat_id}")

    except Exception as e:
        logger.error(f"❌ Webhook Endpoint Error: {e}")
        
    return {"ok": True}
