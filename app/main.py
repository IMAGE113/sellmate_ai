import asyncio
from fastapi import FastAPI
from app.db.database import get_db_pool, init_db
from app.api.webhook import router
from app.workers.order_worker import run_worker

app = FastAPI()
app.include_router(router)

@app.on_event("startup")
async def startup():
    pool = await get_db_pool()
    await init_db(pool)
    asyncio.create_task(run_worker())

@app.get("/")
async def root():
    return {"status":"online"}
