from ai4burmese import Predictor

# model (ပိတောက် / Burmese intent model)
predictor = Predictor(model="padauk")

def detect_intent(text: str):
    result = predictor.predict(text)

    """
    expected output example:
    {
        "intent": "ORDER",
        "confidence": 0.92
    }
    """

    return result.get("intent", "CHAT")
