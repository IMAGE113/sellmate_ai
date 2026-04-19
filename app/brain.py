from .intent import detect_intent
from .ai import ask_ai


async def process_message(text: str):

    ai = await ask_ai(text)

    # AI4BURMESE FLOW
    if ai.get("source") == "ai4burmese":
        intent = ai["result"].get("intent")

        if intent == "order":
            return {
                "type": "order_flow",
                "engine": "ai4burmese"
            }

    # NORMAL FLOW
    intent = detect_intent(text)

    return {
        "type": "chat",
        "intent": intent,
        "ai": ai
    }
