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
        # ၁။ Multi-tenant အတွက် လိုအပ်သော Table များ အကုန်လုံးကို ဆောက်ပေးခြင်း
        await conn.execute("""
            -- ဆိုင်အချက်အလက်များ သိမ်းဆည်းရန်
            CREATE TABLE IF NOT EXISTS businesses (
                id SERIAL PRIMARY KEY,
                shop_name TEXT,
                tg_bot_token TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- ဆိုင်တစ်ခုချင်းစီ၏ Menu များ သိမ်းဆည်းရန်
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                name TEXT,
                price INTEGER
            );

            -- AI လုပ်ဆောင်ရန်အတွက် Task Queue
            CREATE TABLE IF NOT EXISTS task_queue (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                chat_id TEXT,
                user_text TEXT,
                status TEXT DEFAULT 'pending',
                request_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- ယာယီ Order များ (AI မှ တွက်ချက်ထားသော JSON)
            CREATE TABLE IF NOT EXISTS pending_orders (
                id SERIAL PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                chat_id TEXT,
                order_data JSONB,
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT unique_chat_business UNIQUE (chat_id, business_id)
            );

            -- အတည်ပြုပြီးသော Order များ
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
        
        print("✅ Database Tables & Schema are ready!")
