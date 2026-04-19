from pydantic import BaseModel

class BusinessCreate(BaseModel):
    name: str

class ProductCreate(BaseModel):
    business_id: int
    name: str
    price: float
    stock: int

class OrderCreate(BaseModel):
    business_id: int
    product_id: int
    qty: int
