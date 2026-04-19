from fastapi import FastAPI
from contextlib import asynccontextmanager
from .database import get_db_pool, init_db

# App lifecycle (startup/shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await get_db_pool()
    await init_db(app.state.db_pool)
    yield
    await app.state.db_pool.close()

app = FastAPI(
    title="SellMate AI",
    description="Multi-tenant AI Commerce System",
    version="1.0",
    lifespan=lifespan
)

# Root check
@app.get("/")
async def root():
    return {
        "message": "SellMate AI is live",
        "status": "database initialized",
        "mode": "production-ready"
    }

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}
