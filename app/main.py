import hashlib
import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from .database import get_db_pool, init_db
from .worker import run_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def start_worker_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_worker())
    except Exception as e:
        logger.error(f"❌ Worker Thread Crash: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ၁။ Web Service အတွက် Pool ယူမယ်
    app.state.pool = await get_db_pool(for_worker=False)
    
    # ၂။ Table initialization အရင်လုပ်မယ်
    await init_db(app.state.pool)
    
    # ၃။ ပြီးမှ Worker Thread ကို စမယ်
    worker_thread = threading.Thread(target=start_worker_thread, daemon=True)
    worker_thread.start()
    logger.info("🚀 System fully online with Dual Pool Mode.")

    yield
    if hasattr(app.state, "pool"):
        await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Sellmate AI is running"}

@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        msg = data.get("message", {})
        text = msg.get("text")
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")

        if text and chat_id:
            req_hash = hashlib.md5(f"{chat_id}:{message_id}".encode()).hexdigest()
            async with app.state.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO task_queue (shop_id, chat_id, user_text, request_hash) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                    1, str(chat_id), text, req_hash
                )
                logger.info(f"📥 Task Queued: {chat_id}")
    except Exception as e:
        logger.error(f"❌ Webhook Error: {e}")
    return {"ok": True}
