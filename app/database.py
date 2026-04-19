import asyncpg
import os
import logging

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

# Global pool variable
pool = None 

async def get_db_pool():
    global pool
    if pool is None:
        try:
            # SSL 'require' က Render/Neon အတွက် မဖြစ်မနေလိုအပ်ပါတယ်
            pool = await asyncpg.create_pool(
                DATABASE_URL, 
                ssl='require',
                min_size=1,
                max_size=10
            )
            logger.info("✅ Database pool initialized.")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise e
    return pool

async def init_db(db_pool):
    """Table တွေကို စနစ်တကျ အစီအစဉ်တိုင်း ဆောက်ပေးမယ့် function"""
    async with db_pool.acquire() as conn:
        logger.info("🛠️ Initializing Database Tables...")
        
        # ⚠️ အောက်က line က table အဟောင်းတွေကို ဖျက်တာပါ။ (Data တွေရှိလာရင် comment ပိတ်ထားပါ)
        await conn.execute("DROP TABLE IF EXISTS task_queue, orders, products, businesses CASCADE")

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

        # 4. Task Queue Table (Worker အတွက် အသက်သွေးကြော)
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
        
        # Default Shop ID = 1 ကို ထည့်သွင်းမယ် (ForeignKey Error မတက်အောင်)
        await conn.execute('''
        INSERT INTO businesses (id, name) VALUES (1, 'Randy Cafe')
        ON CONFLICT (id) DO NOTHING;
        ''')
        
        logger.info("✅ All Database Tables are ready.")
