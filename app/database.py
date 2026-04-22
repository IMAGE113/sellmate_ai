import asyncpg, os

pool = None

async def get_db_pool():
    global pool
    if not pool:
        pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    return pool

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS task_queue (...);""")
