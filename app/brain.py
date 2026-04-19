from .intent import detect_intent
from .ai import ask_gemini

def process_message(text: str):

    intent = detect_intent(text)

    # 1. ORDER FLOW
    if intent == "ORDER":
        prompt = f"""
You are SellMate AI order system.
Extract product name and quantity.

User: {text}
Return structured JSON only.
"""
        return ask_gemini(prompt)

    # 2. QUERY FLOW
    if intent == "QUERY":
        return "ဈေးနှုန်းစနစ်ကို စစ်ပေးမယ်"

    # 3. CHAT FLOW
    return ask_gemini(text)
