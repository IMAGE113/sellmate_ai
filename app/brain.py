from .ai import get_chat
from .intent import detect_intent

chat_store = {}

def get_session(chat_id: str):
    if chat_id not in chat_store:
        chat_store[chat_id] = get_chat()
    return chat_store[chat_id]


async def handle_message(chat_id: str, text: str, db_pool):
    intent = detect_intent(text)
    chat = get_session(chat_id)

    # ORDER FLOW
    if intent == "ORDER":
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (chat_id, message) VALUES ($1, $2)",
                chat_id, text
            )
        return "အော်ဒါလက်ခံပြီးပါပြီ ✅"

    # CHAT FLOW
    response = chat.send_message(text)
    return response.text
