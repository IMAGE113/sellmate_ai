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
            # Render မှာ Neon သုံးရင် ssl='require' က မဖြစ်မနေလိုအပ်ပါတယ်
            pool = await asyncpg.create_pool(
                DATABASE_URL, 
                ssl='require',
                min_size=1,
                max_size=10
            )
            logger.info("✅ Database pool initialized.")
            
            # Pool ဆောက်ပြီးတာနဲ့ Table တွေ ရှိမရှိ စစ်မယ်/ဆောက်မယ်
            await init_db(pool)
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise e
    return pool

async def init_db(pool):
    async with pool.acquire() as conn:
        logger.info("🛠️ Initializing Database Tables...")
        
        # --- ⚠️ သတိပြုရန် ---
        # အောက်က CASCADE line က table အဟောင်းတွေကို ဖျက်တာပါ။ 
        # Production ရောက်လို့ data တွေ အရေးကြီးလာရင် ဒီ line ကို comment ပိတ်လိုက်ပါ (#)
        await conn.execute("DROP TABLE IF EXISTS task_queue, orders, products, businesses CASCADE")

        # 1. Businesses (Shops) Table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT,
            api_key TEXT UNIQUE,
            admin_chat_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # 2. Products (Inventory) Table
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

        # 4. Task Queue Table (ဒါက Bot စာပြန်ဖို့အတွက် အဓိကပဲ)
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
        INSERT INTO businesses (id, name, api_key) 
        VALUES (1, 'Randy Cafe', 'default-key-123')
        ON CONFLICT (id) DO NOTHING;
        ''')
        
        logger.info("✅ All tables are ready.")
