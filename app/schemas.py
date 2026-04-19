from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    price: float
    stock: int
    code: str


class OrderCreate(BaseModel):
    product_id: int
    qty: int
    total: float
    payment_type: str
