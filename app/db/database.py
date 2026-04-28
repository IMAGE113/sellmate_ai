import asyncpg
from app.core.config import DATABASE_URL

pool = None

async def get_db_pool():
    global pool
    if not pool:
        pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT,
            tg_bot_token TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT,
            price INTEGER
        );
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            business_id INTEGER,
            chat_id BIGINT,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS pending_orders (
            chat_id BIGINT,
            business_id INTEGER,
            order_data TEXT,
            PRIMARY KEY(chat_id, business_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INTEGER,
            chat_id BIGINT,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            payment_method TEXT,
            items TEXT,
            total_price INTEGER
        );
        """)
