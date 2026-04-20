import asyncpg
import os
import logging

# Logger သတ်မှတ်ခြင်း
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
DATABASE_URL = os.getenv("DATABASE_URL")

# Global Pools
web_pool = None
worker_pool = None

async def get_db_pool(for_worker=False):
    global web_pool, worker_pool
    try:
        if for_worker:
            if worker_pool is None:
                worker_pool = await asyncpg.create_pool(
                    DATABASE_URL, 
                    ssl='require',
                    statement_cache_size=0,
                    min_size=1,
                    max_size=10
                )
            return worker_pool
        else:
            if web_pool is None:
                web_pool = await asyncpg.create_pool(
                    DATABASE_URL, 
                    ssl='require',
                    statement_cache_size=0,
                    min_size=1,
                    max_size=10
                )
            return web_pool
    except Exception as e:
        logger.error(f"Database Pool Error: {e}")
        raise e

async def init_db(pool):
    """
    Database Table များကို Safe ဖြစ်စွာ တည်ဆောက်/ပြင်ဆင်ပေးပါတယ်။
    Data မပျက်စေရန် TRUNCATE/DROP များကို မသုံးထားပါ။
    """
    async with pool.acquire() as conn:
        # 1. Businesses Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT,
            name TEXT, 
            tg_bot_token TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 2. Products Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT,
            price REAL
        );
        """)

        # 3. Orders Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            chat_id BIGINT,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price REAL,
            payment_method TEXT DEFAULT 'COD',
            status TEXT DEFAULT 'pending',
            order_hash TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 4. Pending Orders Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            chat_id BIGINT,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            order_data JSONB,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(chat_id, business_id)
        );
        """)

        # 5. Task Queue Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
            chat_id BIGINT,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            attempts INT DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # --- Safe Migration: Column Type ပြောင်းလဲခြင်း (Data မပျက်စေပါ) ---
        try:
            await conn.execute("""
                ALTER TABLE task_queue ALTER COLUMN chat_id TYPE BIGINT USING chat_id::BIGINT;
                ALTER TABLE pending_orders ALTER COLUMN chat_id TYPE BIGINT USING chat_id::BIGINT;
                ALTER TABLE orders ALTER COLUMN chat_id TYPE BIGINT USING chat_id::BIGINT;
                
                -- JSON ကို JSONB သို့ ပြောင်းရန်
                ALTER TABLE pending_orders ALTER COLUMN order_data TYPE JSONB USING order_data::jsonb;
                ALTER TABLE orders ALTER COLUMN items TYPE JSONB USING items::jsonb;
            """)
        except Exception as e:
            logger.info(f"Migration note (Already up to date): {e}")

        # --- Shop Setup ---
        bot_token = os.getenv("TG_BOT_TOKEN")
        shop_name = os.getenv("SHOP_NAME", "Randy Cafe")
        if bot_token:
            await conn.execute("""
                INSERT INTO businesses (shop_name, name, tg_bot_token) 
                VALUES ($1, $1, $2)
                ON CONFLICT (tg_bot_token) DO UPDATE SET name = EXCLUDED.name
            """, shop_name, bot_token)
        
        logger.info("Multi-tenant Database logic initialized successfully.")
