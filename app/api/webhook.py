import hashlib
import logging
from fastapi import APIRouter, Request, Header, HTTPException
from app.db.database import get_db_pool

router = APIRouter()

@router.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    try:
        data = await request.json()
        pool = await get_db_pool()

        # 1. Callback Query (Buttons) ကို ပုံမှန် Message အဖြစ် ပြောင်းပေးမယ်
        if "callback_query" in data:
            cb = data["callback_query"]
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
            # 2. Token နဲ့ ဆိုင်ရှိမရှိ စစ်မယ် (SaaS Security)
            biz = await conn.fetchrow(
                "SELECT id FROM businesses WHERE tg_bot_token=$1", 
                token
            )
            
            if not biz:
                logging.warning(f"🚫 Unauthorized token attempt: {token[:10]}...")
                return {"ok": False}

            # 3. Idempotency Check (Request တစ်ခုကို နှစ်ခါမလုပ်မိအောင်)
            # chat_id နဲ့ text ကို hash လုပ်ပြီး unique key ထုတ်တယ်
            h = hashlib.md5(f"{chat_id}{user_text}".encode()).hexdigest()

            # 4. Task Queue ထဲ ထည့်မယ်
            # ON CONFLICT DO NOTHING ကြောင့် Telegram က duplicate လွှတ်ရင်လည်း DB မှာ တစ်ခါပဲဝင်မယ်
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, biz["id"], chat_id, user_text, h)

        return {"ok": True}

    except Exception as e:
        logging.error(f"🔥 Webhook Error: {str(e)}")
        # Telegram ဆီကို 200 OK ပဲ ပြန်ပေးသင့်တယ် (မပြရင် သူက ခဏခဏ ပြန်ပို့နေမှာမို့လို့)
        return {"ok": True}

# 🛠️ Optional: ဆိုင်ရှင်အသစ်တွေ Bot လာချိတ်ဖို့ API (SaaS Onboarding)
@router.post("/register-bot")
async def register_bot(token: str, name: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO businesses (name, tg_bot_token) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            name, token
        )
    return {"status": "success", "message": f"Bot {name} registered!"}
