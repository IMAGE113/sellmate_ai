import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute('''

        -- 🏢 Businesses (Tenants)
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            api_key VARCHAR(255) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 📦 Products
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            code VARCHAR(20) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 🧾 Orders (State Machine Ready)
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id),
            qty INTEGER NOT NULL,
            total REAL NOT NULL,
            payment_type VARCHAR(20),
            status VARCHAR(30) DEFAULT 'PENDING_CONFIRMATION',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 💬 Conversations (AI Chatbot Memory)
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
            user_id VARCHAR(100),
            current_step VARCHAR(50),
            data JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ''')
