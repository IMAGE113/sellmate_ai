import asyncpg
import os
import logging

# Environment Variables
DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

# Global Pools
web_pool = None
worker_pool = None

async def get_db_pool(for_worker=False):
    """
    Web server နဲ့ Worker အတွက် Connection Pool ကို ခွဲခြားပြီး စီမံပေးပါတယ်။
    statement_cache_size=0 က Neon/PgBouncer မှာဖြစ်တတ်တဲ့ Schema error ကို ကာကွယ်ပေးပါတယ်။
    """
    global web_pool, worker_pool
    if for_worker:
        if worker_pool is None:
            worker_pool = await asyncpg.create_pool(
                DATABASE_URL, 
                ssl='require',
                statement_cache_size=0
            )
        return worker_pool
    else:
        if web_pool is None:
            web_pool = await asyncpg.create_pool(
                DATABASE_URL, 
                ssl='require',
                statement_cache_size=0
            )
        return web_pool

async def init_db(pool):
    """
    Database Table အားလုံးကို Multi-tenant စနစ်အတွက် တည်ဆောက်ပေးပါတယ်။
    """
    async with pool.acquire() as conn:
        # 1. Businesses Table (Bot Token များကို ဒီမှာသိမ်းမယ်)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT,
            tg_bot_token TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 2. Products Table (ဆိုင်အလိုက် Menu များ)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT,
            price REAL
        );
        """)

        # 3. Orders Table (Confirm ပြီးသား အော်ဒါအစစ်များ)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price REAL,
            order_hash TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 4. Pending Orders Table (CONFIRM မလုပ်ခင် ခေတ္တသိမ်းထားသော အော်ဒါများ)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            chat_id TEXT,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            order_data JSONB,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(chat_id, business_id)
        );
        """)

        # 5. Task Queue Table (Worker အတွက် Queue စနစ်)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            chat_id TEXT,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            attempts INT DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # --- [Auto-Setup] Randy Cafe အတွက် Token ရှိရင် Database ထဲ တန်းထည့်ပေးမယ် ---
        # ဒါကြောင့် SQL Editor မှာ manual သွားရိုက်စရာ မလိုတော့ပါဘူး
        bot_token = os.getenv("TG_BOT_TOKEN")
        shop_name = os.getenv("SHOP_NAME", "Randy Cafe")
        if bot_token:
            await conn.execute("""
                INSERT INTO businesses (shop_name, tg_bot_token) 
                VALUES ($1, $2)
                ON CONFLICT (tg_bot_token) DO NOTHING
            """, shop_name, bot_token)
        
        logger.info("Multi-tenant Database logic initialized.")
