import asyncpg, os

pool = None

async def get_db_pool():
    global pool
    if not pool:
        pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    return pool

async def init_db(pool):
    async with pool.acquire() as conn:
        # 1. Businesses Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            tg_bot_token TEXT UNIQUE NOT NULL,
            webhook_secret TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 2. Products Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 3. Task Queue Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            chat_id BIGINT,
            user_text TEXT,
            request_hash TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 4. Pending Orders (AI Memory)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            chat_id BIGINT,
            business_id INTEGER,
            order_data TEXT,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (chat_id, business_id)
        );
        """)

        # 5. Final Orders Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            chat_id BIGINT,
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            payment_method TEXT,
            items TEXT,
            total_price INTEGER,
            order_hash TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 6. Subscriptions Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            business_id INTEGER UNIQUE REFERENCES businesses(id) ON DELETE CASCADE,
            plan_type TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active',
            order_limit INTEGER DEFAULT 100,
            current_usage INTEGER DEFAULT 0,
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '30 days',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        print("✅ Database Tables Initialized Successfully")
