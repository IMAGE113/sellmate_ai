import hashlib, os
from fastapi import FastAPI, Request
from .database import get_db_pool # မင်းဆီက db connection pool

app = FastAPI()

@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    data = await req.json()
    msg = data.get("message", {})
    text = msg.get("text", "")
    chat_id = str(msg.get("chat", {}).get("id", ""))
    message_id = msg.get("message_id")

    if not text: return {"ok": True}

    # IDEMPOTENCY GUARD: Message ID နဲ့ Hash လုပ်ပြီး duplicate တားမယ်
    req_hash = hashlib.md5(f"{chat_id}:{message_id}".encode()).hexdigest()

    async with app.state.pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO task_queue (shop_id, chat_id, user_text, request_hash) VALUES ($1, $2, $3, $4)",
                1, chat_id, text, req_hash
            )
        except:
            # Duplicate message ဆိုရင် ignore လုပ်မယ်
            pass
            
    return {"ok": True}
