from fastapi import FastAPI, Depends, Header, HTTPException
from contextlib import asynccontextmanager

from .database import get_db_pool, init_db
from .schemas import ProductCreate, OrderCreate
from .auth import generate_api_key

app = FastAPI(title="SellMate AI")


# -------------------------
# DB INIT
# -------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


# -------------------------
# DB Dependency
# -------------------------
async def get_db():
    async with app.state.pool.acquire() as conn:
        yield conn


# -------------------------
# HEALTH CHECK
# -------------------------
@app.get("/")
async def root():
    return {"status": "SellMate AI Running 🚀"}


# -------------------------
# BUSINESS SETUP
# -------------------------
@app.post("/setup/business")
async def create_business(name: str, db=Depends(get_db)):
    api_key = generate_api_key()

    business_id = await db.fetchval(
        "INSERT INTO businesses (name, api_key) VALUES ($1, $2) RETURNING id",
        name,
        api_key
    )

    return {
        "business_id": business_id,
        "api_key": api_key
    }


# -------------------------
# ADD PRODUCT
# -------------------------
@app.post("/product")
async def add_product(
    product: ProductCreate,
    business_id: int = Header(...),
    db=Depends(get_db)
):
    pid = await db.fetchval("""
        INSERT INTO products (business_id, name, price, stock, code)
        VALUES ($1,$2,$3,$4,$5)
        RETURNING id
    """, business_id, product.name, product.price, product.stock, product.code)

    return {"product_id": pid}


# -------------------------
# CREATE ORDER
# -------------------------
@app.post("/order")
async def create_order(
    order: OrderCreate,
    business_id: int = Header(...),
    db=Depends(get_db)
):
    stock = await db.fetchval(
        "SELECT stock FROM products WHERE id=$1 AND business_id=$2",
        order.product_id,
        business_id
    )

    if stock is None:
        raise HTTPException(404, "Product not found")

    if stock < order.qty:
        raise HTTPException(400, "Not enough stock")

    order_id = await db.fetchval("""
        INSERT INTO orders (business_id, product_id, qty, total, payment_type)
        VALUES ($1,$2,$3,$4,$5)
        RETURNING id
    """, business_id, order.product_id, order.qty, order.total, order.payment_type)

    await db.execute(
        "UPDATE products SET stock = stock - $1 WHERE id=$2",
        order.qty,
        order.product_id
    )

    return {
        "order_id": order_id,
        "status": "PENDING"
    }
