from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager

from .database import get_pool, init_db
from .schemas import BusinessCreate, ProductCreate, OrderCreate
from .auth import generate_api_key
from .ai import ask_gemini

app = FastAPI()

# DB
pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await get_pool()
    await init_db(pool)
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)


# ---------------- BUSINESS ----------------
@app.post("/business/create")
async def create_business(data: BusinessCreate):
    api_key = generate_api_key()

    async with pool.acquire() as conn:
        bid = await conn.fetchval(
            "INSERT INTO businesses (name, api_key) VALUES ($1, $2) RETURNING id",
            data.name, api_key
        )

    return {"business_id": bid, "api_key": api_key}


# ---------------- PRODUCTS ----------------
@app.post("/product/add")
async def add_product(data: ProductCreate):
    async with pool.acquire() as conn:
        pid = await conn.fetchval("""
            INSERT INTO products (business_id, name, price, stock)
            VALUES ($1,$2,$3,$4) RETURNING id
        """, data.business_id, data.name, data.price, data.stock)

    return {"product_id": pid}


# ---------------- ORDERS ----------------
@app.post("/order/create")
async def create_order(data: OrderCreate):
    async with pool.acquire() as conn:

        price = await conn.fetchval(
            "SELECT price FROM products WHERE id=$1",
            data.product_id
        )

        total = price * data.qty

        oid = await conn.fetchval("""
            INSERT INTO orders (business_id, product_id, qty, total)
            VALUES ($1,$2,$3,$4) RETURNING id
        """, data.business_id, data.product_id, data.qty, total)

    return {"order_id": oid, "total": total}


# ---------------- AI TEST ----------------
@app.post("/ai/test")
async def ai_test(prompt: str):
    return {"reply": ask_gemini(prompt)}
