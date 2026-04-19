import asyncpg
from .config import DATABASE_URL

pool = None


async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    return pool


async def get_conn():
    async with pool.acquire() as conn:
        yield conn


async def init_db():
    async with pool.acquire() as conn:

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT,
            api_key TEXT UNIQUE
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INT,
            name TEXT,
            price FLOAT,
            stock INT
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INT,
            product_id INT,
            qty INT,
            total FLOAT,
            status TEXT DEFAULT 'PENDING'
        );
        """)
