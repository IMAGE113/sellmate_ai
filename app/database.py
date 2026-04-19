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
        logger.info("🛠️ Validating SaaS Database Structure...")
        
        # ၁။ ဆိုင်ရှင်များဇယား
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT NOT NULL,
            owner_chat_id TEXT, 
            is_active BOOLEAN DEFAULT TRUE
        );
        ''')

        # ၂။ ဆိုင်အလိုက် Menu
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
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
        CREATE TABLE IF NOT EXISTS orders (
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
        CREATE TABLE IF NOT EXISTS task_queue (
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
        
        # --- INITIAL DATA FOR TESTING ---
        
        # ဆိုင်ထည့်ခြင်း (ID=1)
        await conn.execute("""
            INSERT INTO businesses (id, shop_name) 
            VALUES (1, 'Randy Cafe') 
            ON CONFLICT (id) DO NOTHING;
        """)

        # စမ်းသပ်ရန် ပစ္စည်း (Menu) များ ထည့်ခြင်း
        # ID=1 (Randy Cafe) အတွက် ပစ္စည်း ၃ ခု
        await conn.execute("""
            INSERT INTO products (business_id, name, price, stock, is_available)
            VALUES 
            (1, 'Espresso', 3500.0, 100, TRUE),
            (1, 'Latte', 4500.0, 50, TRUE),
            (1, 'Cappuccino', 4500.0, 50, TRUE)
            ON CONFLICT DO NOTHING;
        """)

        logger.info("✅ SaaS Database check complete with Initial Menu Items.")
