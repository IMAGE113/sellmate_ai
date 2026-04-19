import asyncpg
import os
import logging

# DATABASE_URL ကို Environment ကနေ ယူမယ်
DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

# Pool တွေကို Global သတ်မှတ်မယ် (Web နဲ့ Worker အတွက် ခွဲထားတာပါ)
web_pool = None 
worker_pool = None

async def get_db_pool(for_worker=False):
    """
    Web Service နဲ့ Worker Thread ကြားမှာ Connection လုမသုံးမိအောင် 
    Pool သီးသန့်စီ ခွဲထုတ်ပေးတဲ့ Function
    """
    global web_pool, worker_pool
    
    if for_worker:
        if worker_pool is None:
            try:
                worker_pool = await asyncpg.create_pool(
                    DATABASE_URL, 
                    ssl='require',
                    min_size=1,
                    max_size=5  # Worker အတွက် connection ၅ ခုစာ သီးသန့်ဖယ်မယ်
                )
                logger.info("✅ Worker DB Pool Created.")
            except Exception as e:
                logger.error(f"❌ Worker Pool failed: {e}")
                raise e
        return worker_pool
    else:
        if web_pool is None:
            try:
                web_pool = await asyncpg.create_pool(
                    DATABASE_URL, 
                    ssl='require',
                    min_size=1,
                    max_size=5  # Webhook အတွက် connection ၅ ခုစာ သီးသန့်ဖယ်မယ်
                )
                logger.info("✅ Web DB Pool Created.")
            except Exception as e:
                logger.error(f"❌ Web Pool failed: {e}")
                raise e
        return web_pool

async def init_db(pool):
    """
    Startup မှာ Table တွေ ရှိမရှိ စစ်မယ်၊ မရှိရင် ဆောက်မယ်။
    Main.py က lifespan ထဲမှာ တစ်ကြိမ်ပဲ ခေါ်ရပါမယ်။
    """
    async with pool.acquire() as conn:
        logger.info("🛠️ Checking/Initializing Database Tables...")
        
        # --- ⚠️ CASCADE Table Cleanup (Testing အတွက်ပဲ သုံးပါ) ---
        # await conn.execute("DROP TABLE IF EXISTS task_queue, orders, products, businesses CASCADE")

        # 1. Businesses Table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT,
            api_key TEXT UNIQUE,
            admin_chat_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # 2. Products Table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            code TEXT
        );
        ''')

        # 3. Orders Table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            items JSONB,
            total REAL DEFAULT 0,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # 4. Task Queue Table (Worker အတွက် အဓိက)
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            shop_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            chat_id TEXT NOT NULL,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        
        # အစမ်းသုံးဖို့ Shop ID = 1 ကို တစ်ခါတည်း ထည့်ပေးထားမယ်
        await conn.execute('''
        INSERT INTO businesses (id, name) VALUES (1, 'Randy Cafe')
        ON CONFLICT (id) DO NOTHING;
        ''')
        
        logger.info("✅ Database Initialization Complete.")
