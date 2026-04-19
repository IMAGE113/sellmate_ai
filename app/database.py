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
            worker_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require', min_size=1, max_size=10)
        return worker_pool
    else:
        if web_pool is None:
            web_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require', min_size=1, max_size=10)
        return web_pool

async def init_db(pool):
    async with pool.acquire() as conn:
        logger.info("🛠️ Initializing SaaS Database Tables...")
        
        # ⚠️ အရေးကြီး - Column Error တက်နေလို့ Table အဟောင်းတွေကို အရင်ဖျက်မယ်
        # တစ်ခါ အောင်မြင်သွားရင် ဒီ DROP lines တွေကို ပြန်ဖျက်လို့ရပါတယ်
        await conn.execute("DROP TABLE IF EXISTS task_queue CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS orders CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS products CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS businesses CASCADE;")

        # ၁။ ဆိုင်ရှင်များဇယား
        await conn.execute('''
        CREATE TABLE businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT NOT NULL,
            owner_chat_id TEXT, 
            is_active BOOLEAN DEFAULT TRUE
        );
        ''')

        # ၂။ ဆိုင်အလိုက် Menu
        await conn.execute('''
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            is_available BOOLEAN DEFAULT TRUE
        );
        ''')

        # ၃။ အော်ဒါများဇယား
        await conn.execute('''
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price REAL,
            payment_type TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # ၄။ Task Queue
        await conn.execute('''
        CREATE TABLE task_queue (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id),
            chat_id TEXT NOT NULL,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        
        # Initial Data ထည့်မယ်
        await conn.execute("INSERT INTO businesses (id, shop_name) VALUES (1, 'Randy Cafe');")
        logger.info("✅ SaaS Database Tables Re-created Successfully.")
