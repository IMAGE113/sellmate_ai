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
    # Database connection ကို startup မှာ ဆောက်မယ်
    app.state.pool = await get_db_pool()
    await init_db(app.state.pool)
    yield
    # Server ပိတ်ရင် connection ပိတ်မယ်
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "SellMate AI is running"}

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
        # 1. Shop Registration Flow
        if text.startswith("/start"):
            shop_name = text.replace("/start", "").strip() or "My Shop"
            api_key = generate_api_key()
            
            # စစ်မယ်: ဒီ user က အရင်က register လုပ်ဖူးလား
            existing = await conn.fetchrow("SELECT api_key FROM businesses WHERE admin_chat_id = $1", chat_id)
            
            if not existing:
                await conn.execute(
                    "INSERT INTO businesses (name, api_key, admin_chat_id) VALUES ($1,$2,$3)",
                    shop_name, api_key, chat_id
                )
                await send_tg(chat_id, f"✅ *{shop_name}* Registered!\n\nDashboard Login API Key:\n`{api_key}`")
            else:
                await send_tg(chat_id, f"ဒီ Bot က Register လုပ်ပြီးသားပါ။\nYour API Key: `{existing['api_key']}`")
            return {"ok": True}

        # 2. AI Parsing & Database Processing
        # ai.py ကို စာပို့ပြီး JSON ပြန်ယူမယ်
        ai_res = parse_order(text)
        print(f"DEBUG - Raw AI Output: {ai_res}") # Render Log မှာ စစ်ဖို့

        # ဆိုင်အချက်အလက်ကို Database ထဲက ဆွဲထုတ်မယ်
        business = await conn.fetchrow("SELECT id FROM businesses WHERE admin_chat_id = $1", chat_id)
        
        if not business:
            await send_tg(chat_id, "ကျေးဇူးပြု၍ `/start [ဆိုင်နာမည်]` အရင်လုပ်ပေးပါ။")
            return {"ok": True}

        # AI က 'order' လို့ သတ်မှတ်မှသာ Database ထဲ သိမ်းမယ်
        if isinstance(ai_res, dict) and ai_res.get("intent") == "order" and ai_res.get("items"):
            items_list = ai_res["items"]
            
            # Orders table ထဲမှာ data သိမ်းမယ်
            await conn.execute(
                "INSERT INTO orders (business_id, items, status) VALUES ($1, $2, $3)",
                business['id'], json.dumps(items_list), "PENDING"
            )
            
            # Customer ဆီ အော်ဒါအကျဉ်းချုပ် ပြန်ပို့မယ်
            summary = "\n".join([f"• {i['name']} - {i['qty']} ခု" for i in items_list])
            await send_tg(chat_id, f"🛒 *အော်ဒါလက်ခံရရှိပါပြီ!*\n\n{summary}\n\nDashboard မှာ အော်ဒါအခြေအနေကို စစ်ဆေးနိုင်ပါတယ်။")
        
        else:
            # Order မဟုတ်ရင် ဒါမှမဟုတ် AI က နားမလည်ရင် Default message ပြန်ပို့မယ်
            await send_tg(chat_id, "မင်္ဂလာပါရှင်၊ ဘာများ မှာယူချင်ပါသလဲ? (ဥပမာ- Coffee ၂ ခွက်ပေးပါ)")

    return {"ok": True}
