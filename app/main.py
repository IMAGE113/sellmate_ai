import asyncpg, os, logging

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

web_pool = None
worker_pool = None

async def get_db_pool(for_worker=False):
    global web_pool, worker_pool
    if for_worker:
        if worker_pool is None:
            worker_pool = await asyncpg.create_pool(
                DATABASE_URL, ssl='require', statement_cache_size=0
            )
        return worker_pool
    else:
        if web_pool is None:
            web_pool = await asyncpg.create_pool(
                DATABASE_URL, ssl='require', statement_cache_size=0
            )
        return web_pool

# ဆိုင်အသစ်တွေကို Database ထဲထည့်ပေးမယ့် Function (Main.py ကနေ ခေါ်သုံးလို့ရအောင်)
async def register_business(pool, shop_name, token):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO businesses (shop_name, tg_bot_token)
            VALUES ($1, $2)
            ON CONFLICT (tg_bot_token) DO UPDATE SET shop_name = $1
        """, shop_name, token)
        logger.info(f"Business {shop_name} registered/updated.")

async def init_db(pool):
    async with pool.acquire() as conn:
        # 1. Businesses Table (Bot Token တွေကို ဒီမှာသိမ်းမယ်)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            shop_name TEXT,
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
            business_id INT REFERENCES businesses(id),
            customer_name TEXT,
            phone_no TEXT,
            address TEXT,
            items JSONB,
            total_price REAL,
            order_hash TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 4. Pending Orders Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            chat_id TEXT,
            business_id INT REFERENCES businesses(id),
            order_data JSONB,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(chat_id, business_id)
        );
        """)

        # 5. Task Queue Table (Main.py က request_hash နဲ့ conflict မဖြစ်အောင် စစ်ဖို့)
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
        
        # --- [စမ်းသပ်ရန်] Randy Cafe ကို အလိုအလျောက် ထည့်သွင်းပေးခြင်း ---
        # ဖွင့်ထားတဲ့ Env ထဲမှာ SHOP_NAME နဲ့ TG_BOT_TOKEN ရှိရင် Database ထဲ တန်းထည့်ပေးမယ်
        shop_name = os.getenv("SHOP_NAME", "Randy Cafe")
        bot_token = os.getenv("TG_BOT_TOKEN")
        if bot_token:
            await conn.execute("""
                INSERT INTO businesses (shop_name, tg_bot_token) 
                VALUES ($1, $2)
                ON CONFLICT (tg_bot_token) DO NOTHING
            """, shop_name, bot_token)
