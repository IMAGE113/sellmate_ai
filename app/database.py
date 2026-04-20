import asyncpg, os, logging

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

web_pool = None
worker_pool = None

async def get_db_pool(for_worker=False):
    global web_pool, worker_pool
    if for_worker:
        if worker_pool is None:
            worker_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        return worker_pool
    else:
        if web_pool is None:
            web_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        return web_pool

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT,
            tg_bot_token TEXT UNIQUE
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INT,
            name TEXT,
            price REAL
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INT,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price REAL,
            order_hash TEXT UNIQUE
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            chat_id TEXT,
            business_id INT,
            order_data JSONB,
            PRIMARY KEY(chat_id, business_id)
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            business_id INT,
            chat_id TEXT,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            attempts INT DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)
