import os
from google import genai

# =========================
# GEMINI CLIENT SETUP
# =========================
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# =========================
# AI4BURMESE (OPTIONAL HOOK)
# =========================
try:
    from ai4burmese import Predictor
    predictor = Predictor(model="padauk")
except Exception:
    predictor = None


# =========================
# INTENT DETECTION
# =========================
def detect_intent(text: str) -> str:
    """
    Detect Burmese intent using ai4burmese if available,
    otherwise fallback to simple rule-based detection.
    """

    if predictor:
        try:
            result = predictor.predict(text)
            return result.get("intent", "CHAT")
        except Exception:
            pass

    # fallback (safe basic rules)
    text_lower = text.lower()

    if any(word in text_lower for word in ["ဝယ်", "မှာ", "order", "ယူချင်"]):
        return "ORDER"

    if any(word in text_lower for word in ["ဈေး", "price", "ဘယ်လောက်"]):
        return "QUERY"

    return "CHAT"


# =========================
# GEMINI CORE CALL
# =========================
def ask_gemini(prompt: str) -> str:
    """
    Main reasoning engine (Gemini 1.5 Flash recommended)
    """

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt
    )

    return response.text


# =========================
# ORDER PARSER (STRUCTURED OUTPUT)
# =========================
def extract_order(text: str) -> str:
    """
    Convert natural language → structured order JSON (via Gemini)
    """

    prompt = f"""
You are SellMate AI order parser.

Extract structured order data from this user message.

Return ONLY JSON in this format:
{{
  "product": "",
  "quantity": 0
}}

User message:
{text}
"""

    return ask_gemini(prompt)


# =========================
# MAIN BRAIN ROUTER
# =========================
def process_message(text: str) -> str:
    """
    Main entry point for SellMate AI brain
    """

    intent = detect_intent(text)

    # -------------------------
    # ORDER FLOW
    # -------------------------
    if intent == "ORDER":
        return extract_order(text)

    # -------------------------
    # QUERY FLOW (price, stock)
    # -------------------------
    if intent == "QUERY":
        prompt = f"""
You are SellMate AI assistant.

User is asking about price or product info.

Answer clearly in Burmese.

User: {text}
"""
        return ask_gemini(prompt)

    # -------------------------
    # CHAT FLOW (normal talk)
    # -------------------------
    return ask_gemini(text)
