import asyncpg, os, logging

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

pool = None

async def get_db_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            DATABASE_URL,
            ssl='require',
            min_size=1,
            max_size=10
        )
    return pool

async def init_db(pool):
    async with pool.acquire() as conn:
        logger.info("✅ Initializing Database...")

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT NOT NULL,
            tg_bot_token TEXT UNIQUE NOT NULL
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT,
            price INT
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
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INT,
            chat_id TEXT,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price INT,
            payment_method TEXT,
            order_hash TEXT UNIQUE
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
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
