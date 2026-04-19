import asyncpg
import os
import logging

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

web_pool = None 
worker_pool = None

async def get_db_pool(for_worker=False):
    global web_pool, worker_pool
    if for_worker:
        if worker_pool is None:
            worker_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require', min_size=1, max_size=5)
        return worker_pool
    else:
        if web_pool is None:
            web_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require', min_size=1, max_size=5)
        return web_pool

async def init_db(pool):
    async with pool.acquire() as conn:
        logger.info("🛠️ Initializing Updated Tables...")
        # Businesses
        await conn.execute('CREATE TABLE IF NOT EXISTS businesses (id SERIAL PRIMARY KEY, name TEXT);')
        
        # Products (Menu & Stock Control)
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            is_available BOOLEAN DEFAULT TRUE
        );
        ''')

        # Orders (Dashboard အတွက် အသေးစိတ်)
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price REAL,
            payment_type TEXT, -- COD or Preorder
            status TEXT DEFAULT 'PENDING', -- PENDING, SHIPPED, COMPLETED
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # Task Queue
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY, chat_id TEXT NOT NULL, user_text TEXT, 
            request_hash TEXT UNIQUE, status TEXT DEFAULT 'pending', 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        logger.info("✅ Database Structure Updated.")
