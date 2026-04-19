import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from dotenv import load_dotenv

import httpx
import aiosqlite

# AI (Gemini)
from google import genai
from google.genai import types

# ================== ENV ==================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PORT = int(os.getenv("PORT", 10000))

logging.basicConfig(level=logging.INFO)

# ================== AI CLIENT ==================
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ================== LOCAL DB ==================
DB_FILE = "sellmate.db"

# ================== MEMORY ==================
user_sessions = {}
telegram_queue = asyncio.Queue()

# ================== SIMPLE MENU (TEMP) ==================
MENU = {
    "coffee": {"price": 1500, "stock": 10},
    "cola": {"price": 1000, "stock": 20}
}

# ================== DATABASE ==================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            items TEXT,
            total REAL,
            status TEXT DEFAULT 'pending'
        )
        """)
        await db.commit()

# ================== TELEGRAM ==================
async def telegram_worker():
    async with httpx.AsyncClient() as client:
        while True:
            chat_id, text = await telegram_queue.get()
            try:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": text}
                )
            except Exception as e:
                logging.error(e)

async def send(chat_id: str, text: str):
    await telegram_queue.put((chat_id, text))

# ================== AI SYSTEM PROMPT ==================
def system_prompt():
    return """
You are SellMate AI assistant.

Rules:
- You are order assistant
- Always help user order products
- Keep replies short
- If product exists, confirm order
"""

# ================== AI CHAT ==================
def get_chat(chat_id: str):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = ai_client.chats.create(
            model="gemini-1.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt(),
                temperature=0.5
            )
        )
    return user_sessions[chat_id]

# ================== ORDER SAVE ==================
async def save_order(chat_id: str, items: str, total: float):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO orders (chat_id, items, total) VALUES (?, ?, ?)",
            (chat_id, items, total)
        )
        await db.commit()
    return {"status": "saved"}

# ================== AI HANDLER ==================
async def handle_ai(chat_id: str, text: str):
    chat = get_chat(chat_id)

    response = await asyncio.to_thread(
        chat.send_message,
        text
    )

    return response.text

# ================== WEBHOOK ==================
app = FastAPI()

@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(telegram_worker())

@app.post("/webhook")
async def webhook(req: Request, bg: BackgroundTasks):
    data = await req.json()

    msg = data.get("message", {})
    text = msg.get("text")
    chat_id = str(msg.get("chat", {}).get("id"))

    if not text:
        return {"ok": True}

    reply = await handle_ai(chat_id, text)

    await send(chat_id, reply)

    return {"ok": True}

# ================== RUN ==================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
