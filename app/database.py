import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None

async def get_db_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool

async def init_db(pool):
    async with pool.acquire() as conn:
        # ၁။ Table များ အကုန်လုံးကို အလိုအလျောက် ဆောက်ပေးမယ့် SQL
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id SERIAL PRIMARY KEY,
                shop_name TEXT,
                tg_bot_token TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                name TEXT,
                price INTEGER
            );

            CREATE TABLE IF NOT EXISTS task_queue (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                chat_id TEXT,
                user_text TEXT,
                status TEXT DEFAULT 'pending',
                request_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS pending_orders (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                chat_id TEXT,
                order_data JSONB,
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT unique_chat_business UNIQUE (chat_id, business_id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                chat_id TEXT,
                customer_name TEXT,
                phone_no TEXT,
                address TEXT,
                items JSONB,
                total_price INTEGER,
                payment_method TEXT,
                order_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # ၂။ မင်းရဲ့ Bot Token ကိုပါ တခါတည်း စစ်ပြီး ထည့်ပေးထားမယ်
        await conn.execute("""
            INSERT INTO businesses (shop_name, tg_bot_token) 
            VALUES ('Randy Cafe', '8789177063:AAHwEQlTSROeM-qD-zzrpFB5UKSLEFwo0jE')
            ON CONFLICT (tg_bot_token) DO NOTHING;
        """)
        
        print("✅ Database Tables & Initial Data are ready!")
