from .ai import get_gemini_chat
from .intent import detect_intent

sessions = {}

def get_session(chat_id: str):
    if chat_id not in sessions:
        sessions[chat_id] = get_gemini_chat()
    return sessions[chat_id]


async def process_message(chat_id: str, text: str):

    intent = detect_intent(text)
    chat = get_session(chat_id)

    # ORDER FLOW (simple logic now)
    if intent == "ORDER":
        response = chat.send_message(
            f"User wants to order: {text}"
        )
        return response.text

    # STOCK FLOW
    if intent == "STOCK":
        return "Stock system coming next step."

    # CHAT FLOW
    response = chat.send_message(text)
    return response.text
