# ai4burmese integration layer (REAL PLACE)

def detect_intent(text: str):
    text = text.lower()

    if "order" in text or "ဝယ်" in text:
        return "ORDER"

    if "stock" in text:
        return "STOCK"

    return "CHAT"
