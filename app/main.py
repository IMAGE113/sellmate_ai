import os
import json
import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from .database import get_db_pool, init_db
from .ai import parse_order
from .auth import generate_api_key

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_tg(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "SellMate AI is online"}

@app.post("/webhook/telegram")
async def webhook(req: Request):
    try:
        data = await req.json()
    except:
        return {"ok": True}

    msg = data.get("message", {})
    text = msg.get("text", "")
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if not text:
        return {"ok": True}

    async with app.state.pool.acquire() as conn:
        # 1. Register ဆိုင်မှတ်ပုံတင်ခြင်း
        if text.startswith("/start"):
            shop_name = text.replace("/start", "").strip() or "My Shop"
            api_key = generate_api_key()
            
            existing = await conn.fetchrow("SELECT api_key FROM businesses WHERE admin_chat_id = $1", chat_id)
            
            if not existing:
                await conn.execute(
                    "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3)",
                    shop_name, api_key, chat_id
                )
                await send_tg(chat_id, f"✅ *{shop_name}* Registered!\n\nDashboard API Key:\n`{api_key}`")
            else:
                await send_tg(chat_id, f"ဒီ Bot က Register လုပ်ပြီးသားပါ။\nAPI Key: `{existing['api_key']}`")
            return {"ok": True}

        # 2. AI Processing
        ai_res = parse_order(text)
        print(f"DEBUG - Final AI Output: {ai_res}")

        business = await conn.fetchrow("SELECT id FROM businesses WHERE admin_chat_id = $1", chat_id)
        if not business:
            await send_tg(chat_id, "ကျေးဇူးပြု၍ `/start [ဆိုင်နာမည်]` အရင်လုပ်ပေးပါ။")
            return {"ok": True}

        # Safety: items စာရင်းပါရင် order လို့ သတ်မှတ်မယ်
        items = ai_res.get("items", [])
        if (ai_res.get("intent") == "order" or len(items) > 0) and items:
            # Database ထဲ သိမ်းမယ်
            await conn.execute(
                "INSERT INTO orders (business_id, items, status) VALUES ($1, $2, $3)",
                business['id'], json.dumps(items), "PENDING"
            )
            
            summary = "\n".join([f"• {i['name']} - {i['qty']} ခု" for i in items])
            await send_tg(chat_id, f"🛒 *အော်ဒါလက်ခံရရှိပါပြီ!*\n\n{summary}\n\nDashboard မှာ စစ်ဆေးနိုင်ပါတယ်။")
        else:
            await send_tg(chat_id, "မင်္ဂလာပါရှင်၊ ဘာများ မှာယူချင်ပါသလဲ? (ဥပမာ- Coffee ၂ ခွက်ပေးပါ)")

    return {"ok": True}
