import httpx

http_client = httpx.AsyncClient(timeout=10)

async def send(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": int(chat_id),
        "text": str(text),
        "parse_mode": "Markdown"
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    await http_client.post(url, json=payload)
