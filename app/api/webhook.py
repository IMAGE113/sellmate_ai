import hashlib
import logging
import httpx  # ✅ answerCallbackQuery ပို့ဖို့ httpx လိုပါတယ်
from fastapi import APIRouter, Request, Header, HTTPException
from app.db.database import get_db_pool

router = APIRouter()

@router.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    try:
        data = await request.json()
        pool = await get_db_pool()

        # 1. Callback Query (Buttons) Logic
        if "callback_query" in data:
            cb = data["callback_query"]
            callback_id = cb["id"]  # ✅ Callback Query ရဲ့ ID ကို ယူမယ်

            # 🚨 ချက်ချင်း Telegram ဆီ answerCallbackQuery ပြန်ပို့ပါ (Loop ပိတ်ဖို့)
            # ဒါမှ "အော်ဒါအတည်ပြုလိုက်ပါပြီ" ဆိုတဲ့စာကြီး တန်းစီတက်မလာတော့မှာပါ
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                    json={"callback_query_id": callback_id}
                )

            # Button နှိပ်တဲ့အခါ message ထဲမှာ text အစား callback data ဝင်သွားအောင် လုပ်တာပါ
            data["message"] = {
                "chat": {"id": cb["message"]["chat"]["id"]},
                "text": cb["data"],
                "from": cb["from"]
            }

        msg = data.get("message")
        if not msg or "text" not in msg:
            return {"ok": True}

        chat_id = msg["chat"]["id"]
        user_text = msg["text"]

        async with pool.acquire() as conn:
            # 2. Token စစ်ဆေးခြင်း
            biz = await conn.fetchrow(
                "SELECT id FROM businesses WHERE tg_bot_token=$1", 
                token
            )
            
            if not biz:
                logging.warning(f"🚫 Unauthorized token attempt: {token[:10]}...")
                return {"ok": False}

            # 3. Idempotency Check (Duplicate ကာကွယ်ရန်)
            h = hashlib.md5(f"{chat_id}{user_text}".encode()).hexdigest()

            # 4. Task Queue ထဲ ထည့်မယ်
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, biz["id"], chat_id, user_text, h)

        return {"ok": True}

    except Exception as e:
        logging.error(f"🔥 Webhook Error: {str(e)}")
        return {"ok": True}

# 🛠️ Register Bot API
@router.post("/register-bot")
async def register_bot(token: str, name: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO businesses (name, tg_bot_token) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            name, token
        )
    return {"status": "success", "message": f"Bot {name} registered!"}
