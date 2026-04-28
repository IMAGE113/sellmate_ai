import asyncio
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db.database import get_db_pool, init_db
from app.api.webhook import router
from app.workers.order_worker import run_worker

# ✅ Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ✅ Lifespan (modern FastAPI way)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Starting SellMate AI...")

    # DB connect + init
    pool = await get_db_pool()
    await init_db(pool)
    logging.info("✅ Database connected")

    # Start worker
    worker_task = asyncio.create_task(run_worker())
    logging.info("⚙️ Worker started")

    yield  # ---- app runs here ----

    # Shutdown
    logging.info("🛑 Shutting down...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        logging.info("✅ Worker stopped")

# ✅ App init
app = FastAPI(lifespan=lifespan)

# Routes
app.include_router(router)

# Health check
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "SellMate AI",
        "version": "1.0"
    }

# Optional: deeper health check
@app.get("/health")
async def health():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
