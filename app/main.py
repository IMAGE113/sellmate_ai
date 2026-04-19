import os
import asyncio
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import httpx

from .database import connect_db, init_db
from .brain import process_message

load_dotenv()

app = FastAPI()

telegram_queue = asyncio.Queue()


# ---------------- TELEGRAM ----------------
async def telegram_worker():
    async with httpx.AsyncClient() as client:
        while True:
            chat_id, text = await telegram_queue.get()
            try:
                await client.post(
                    f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
                    json={"chat_id": chat_id, "text": text}
                )
            except:
                pass


async def send(chat_id, text):
    await telegram_queue.put((chat_id, text))


# ---------------- STARTUP ----------------
@app.on_event("startup")
async def startup():
    await connect_db()
    await init_db()
    asyncio.create_task(telegram_worker())


# ---------------- WEBHOOK ----------------
@app.post("/webhook")
async def webhook(req: Request):

    data = await req.json()
    msg = data.get("message", {})

    text = msg.get("text")
    chat_id = str(msg.get("chat", {}).get("id"))

    if not text:
        return {"ok": True}

    reply = await process_message(chat_id, text)

    await send(chat_id, reply)

    return {"ok": True}


# ---------------- RUN ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
