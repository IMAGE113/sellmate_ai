import asyncpg
import os
import logging

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

# Pool ၂ ခု ခွဲသတ်မှတ်မယ်
web_pool = None 
worker_pool = None

async def get_db_pool(for_worker=False):
    global web_pool, worker_pool
    
    if for_worker:
        if worker_pool is None:
            worker_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require', min_size=1, max_size=5)
            logger.info("✅ Worker DB Pool Created.")
        return worker_pool
    else:
        if web_pool is None:
            web_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require', min_size=1, max_size=5)
            logger.info("✅ Web DB Pool Created.")
        return web_pool

async def init_db(pool):
    async with pool.acquire() as conn:
        logger.info("🛠️ Initializing Database Tables...")
        
        # Businesses Table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY, name TEXT, api_key TEXT UNIQUE, admin_chat_id TEXT UNIQUE
        );
        ''')

        # Task Queue Table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY, shop_id INTEGER, chat_id TEXT NOT NULL, user_text TEXT, 
            request_hash TEXT UNIQUE, status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, 
            last_error TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        
        await conn.execute("INSERT INTO businesses (id, name) VALUES (1, 'Randy Cafe') ON CONFLICT (id) DO NOTHING;")
        logger.info("✅ Database Tables are Ready.")
