from pydantic import BaseModel

class Message(BaseModel):
    chat_id: str
    text: str
