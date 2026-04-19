from pydantic import BaseModel

class BusinessCreate(BaseModel):
    name: str

class ProductCreate(BaseModel):
    name: str
    price: float
    stock: int

class OrderCreate(BaseModel):
    product: str
    qty: int
