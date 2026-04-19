import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        # --- အရေးကြီးသည် ---
        # အောက်က line က table တွေကို အသစ်ပြန်ဆောက်ဖို့ အဟောင်းတွေကို ဖျက်ထုတ်တာပါ။
        # တစ်ခါ Deploy ဖြစ်ပြီး Bot စာပြန်ပြီဆိုရင် ဒီ line ကို ပြန်ဖျက်ပေးပါ။
        await conn.execute("DROP TABLE IF EXISTS orders, products, businesses CASCADE")

        # 1. Shop/Business Table
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
