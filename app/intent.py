from ai4burmese import IntentClassifier

classifier = IntentClassifier(model="padauk")

def detect_intent(text: str):
    try:
        return classifier.predict(text)
    except:
        text = text.lower()

        if "order" in text or "ဝယ်" in text:
            return "ORDER"

        if "cancel" in text:
            return "CANCEL"

        return "CHAT"
