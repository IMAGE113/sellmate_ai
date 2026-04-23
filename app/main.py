import hashlib
import os
import asyncio
from fastapi import FastAPI, Request
from telegram import InlineKeyboardMarkup, InlineKeyboardButton # ✅ Added
from .database import get_db_pool, init_db
from .worker import run_worker

app = FastAPI()
db_pool = None

# ✅ NEW HELPER: UI Button Generator
def get_ui_markup(ui_type):
    """ai.py က လှမ်းပို့လိုက်တဲ့ ui flag အပေါ်မူတည်ပြီး Button ဆောက်ပေးခြင်း"""
    if ui_type == "confirm_buttons":
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm Order", callback_data="confirm"),
                InlineKeyboardButton("🔄 Restart", callback_data="restart")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    elif ui_type == "main_menu":
        keyboard = [[InlineKeyboardButton("📜 View Menu", callback_data="view_menu")]]
        return InlineKeyboardMarkup(keyboard)
        
    return None

@app.on_event("startup")
async def startup_event():
    global db_pool
    db_pool = await get_db_pool()
    await init_db(db_pool)
    
    asyncio.create_task(run_worker())
    print("🚀 SellMate AI Server & Worker started successfully!")

@app.get("/")
async def root():
    return {
        "status": "online", 
        "service": "SellMate AI",
        "timestamp": os.getenv("RENDER_START_TIME", "active")
    }

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    global db_pool
    if not db_pool:
        db_pool = await get_db_pool()

    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    # ✅ Handle Callback Query (Button Clicks)
    if "callback_query" in data:
        cb = data["callback_query"]
        # Button နှိပ်လိုက်တဲ့ data ကို text အဖြစ်ပြောင်းပြီး task_queue ထဲ ထည့်လိုက်မယ်
        # ဒါမှ worker ဘက်က AI က 'confirm' ဆိုတဲ့စာကို parse လုပ်နိုင်မှာပါ
        message_to_queue = {
            "chat": {"id": cb["message"]["chat"]["id"]},
            "text": cb["data"] # 'confirm' or 'restart'
        }
        data["message"] = message_to_queue

    async with db_pool.acquire() as conn:
        biz = await conn.fetchrow("SELECT id FROM businesses WHERE tg_bot_token=$1", token)
        if not biz:
            return {"ok": False, "error": "Business not found"}

        b_id = biz['id']
        message = data.get("message") or data.get("edited_message")
        
        if not message or "text" not in message:
            return {"ok": True}

        raw_chat_id = message["chat"]["id"]
        text = message["text"]
        
        hash_input = str(b_id) + ":" + str(raw_chat_id) + ":" + str(text)
        h = hashlib.md5(hash_input.encode()).hexdigest()

        try:
            clean_chat_id = int(raw_chat_id)
        except (ValueError, TypeError):
            clean_chat_id = str(raw_chat_id)

        # 2. Task Queue ထဲသို့ ထည့်သွင်းခြင်း
        try:
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, clean_chat_id, text, h)
        except Exception:
            await conn.execute("""
                INSERT INTO task_queue (business_id, chat_id, user_text, request_hash, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (request_hash) DO NOTHING
            """, b_id, str(raw_chat_id), text, h)

    return {"ok": True}
