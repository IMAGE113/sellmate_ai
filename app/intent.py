def detect_intent(text: str):
    t = text.lower()

    if "မှာ" in t or "order" in t or "ဝယ်" in t:
        return "order"

    if "stock" in t:
        return "stock"

    if "price" in t:
        return "price"

    return "chat"
