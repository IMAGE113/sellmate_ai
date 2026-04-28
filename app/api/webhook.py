import hashlib
from fastapi import APIRouter, Request
from app.db.database import get_db_pool

router = APIRouter()

@router.post("/webhook/{token}")
async def webhook(token:str, request:Request):
    data = await request.json()
    pool = await get_db_pool()

    if "callback_query" in data:
        cb = data["callback_query"]
        data["message"] = {
            "chat":{"id":cb["message"]["chat"]["id"]},
            "text":cb["data"]
        }

    msg = data.get("message")
    if not msg: return {"ok":True}

    async with pool.acquire() as conn:
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        if not biz: return {"ok":False}

        h = hashlib.md5(f"{msg['chat']['id']}{msg['text']}".encode()).hexdigest()

        await conn.execute("""
        INSERT INTO task_queue (business_id, chat_id, user_text, request_hash)
        VALUES ($1,$2,$3,$4)
        ON CONFLICT DO NOTHING
        """, biz["id"], msg["chat"]["id"], msg["text"], h)

    return {"ok":True}
