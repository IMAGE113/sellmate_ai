import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_pool():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL missing")

    return await asyncpg.create_pool(
        DATABASE_URL,
        ssl="require"
    )

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT,
            api_key TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INT,
            chat_id TEXT,
            message TEXT,
            total REAL DEFAULT 0,
            status TEXT DEFAULT 'pending'
        );
        """)
