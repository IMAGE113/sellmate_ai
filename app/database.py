import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute('''

        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT,
            api_key TEXT UNIQUE,
            admin_chat_id TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INTEGER,
            items JSONB,
            total REAL,
            status TEXT DEFAULT 'PENDING'
        );

        ''')
