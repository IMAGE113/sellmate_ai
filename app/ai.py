import google.generativeai as genai
from .config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

# ---------------- AI4BURMESE ----------------
try:
    from ai4burmese import AI4Burmese as AIB
    ai4b = AIB()
except:
    ai4b = None


async def ask_ai(text: str):

    # 1️⃣ AI4BURMESE FIRST (Burmese intent optimized)
    if ai4b:
        try:
            result = ai4b.predict(text)

            if result:
                return {
                    "source": "ai4burmese",
                    "result": result
                }
        except:
            pass

    # 2️⃣ GEMINI FALLBACK
    try:
        res = model.generate_content(text)
        return {
            "source": "gemini",
            "reply": res.text
        }
    except Exception as e:
        return {"error": str(e)}
