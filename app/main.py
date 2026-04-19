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
        await client.post(url, json={"chat_id": chat_id, "text": text})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "SellMate AI is live"}

@app.post("/webhook/telegram")
async def webhook(req: Request):
    data = await req.json()
    msg = data.get("message", {})
    text = msg.get("text", "")
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if not text: return {"ok": True}

    async with app.state.pool.acquire() as conn:
        # 1. Register Shop (Dashboard Access အတွက် API Key ထုတ်ပေးမယ်)
        if text.startswith("/start"):
            shop_name = text.replace("/start", "").strip() or "New Shop"
            api_key = generate_api_key()
            
            # အရင်ရှိပြီးသားလား စစ်မယ်
            biz = await conn.fetchrow("SELECT api_key FROM businesses WHERE admin_chat_id = $1", chat_id)
            
            if not biz:
                await conn.execute(
                    "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3)",
                    shop_name, api_key, chat_id
                )
                await send_tg(chat_id, f"✅ {shop_name} ကို Register လုပ်ပြီးပါပြီ။\n\nDashboard Login API Key:\n`{api_key}`")
            else:
                await send_tg(chat_id, f"ဒီ Bot က Register လုပ်ပြီးသားပါ။\nAPI Key: `{biz['api_key']}`")
            return {"ok": True}

        # 2. AI Parsing & Database Storage (Multi-shop aware)
        ai = parse_order(text)
        
        # ဘယ်ဆိုင်ကလဲဆိုတာ chat_id နဲ့ အရင်ရှာ
        business = await conn.fetchrow("SELECT id FROM businesses WHERE admin_chat_id = $1", chat_id)
        
        if ai["intent"] == "order" and business:
            await conn.execute(
                "INSERT INTO orders (business_id, items, status) VALUES ($1, $2, $3)",
                business['id'], json.dumps(ai["items"]), "PENDING"
            )
            await send_tg(chat_id, f"🛒 အော်ဒါမှတ်သားပြီးပါပြီ- {ai['items']}")
        
        elif not business:
            await send_tg(chat_id, "ကျေးဇူးပြု၍ /start [ဆိုင်နာမည်] အရင်လုပ်ပေးပါ။")
        else:
            await send_tg(chat_id, "ဘာများ မှာယူချင်ပါသလဲရှင်?")

    return {"ok": True}


# ai.py ထဲက parse_order ရဲ့ output ကို log ထုတ်ကြည့်မယ်
        ai = parse_order(text)
        print(f"AI Output: {ai}") # Render log မှာ သွားကြည့်လို့ရအောင်

        if ai["intent"] == "order":
            business = await conn.fetchrow("SELECT id FROM businesses WHERE admin_chat_id = $1", chat_id)
            
            if business:
                # အော်ဒါကို Database ထဲ ထည့်မယ်
                await conn.execute(
                    "INSERT INTO orders (business_id, items, status) VALUES ($1, $2, $3)",
                    business['id'], json.dumps(ai["items"]), "PENDING"
                )
                # Customer ကို အတည်ပြုချက် ပြန်ပို့မယ်
                order_summary = ", ".join([f"{i['name']} ({i['qty']})" for i in ai['items']])
                await send_tg(chat_id, f"🛒 အော်ဒါမှတ်သားပြီးပါပြီ- {order_summary}")
                return {"ok": True}
