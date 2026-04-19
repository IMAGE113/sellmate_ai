import os, json, time, httpx, logging
from google import genai

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.gemini_healthy = True
        self.last_error_time = 0

    async def get_order_json(self, text):
        # 1. Gemini Health Check (Circuit Breaker)
        if not self.gemini_healthy and (time.time() - self.last_error_time < 60):
            return await self.call_groq(text)

        # 2. Try Gemini
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Extract order info into JSON: {text}. Output only JSON."
            )
            self.gemini_healthy = True
            return json.loads(response.text), "gemini"
        except Exception as e:
            if "429" in str(e):
                self.gemini_healthy = False
                self.last_error_time = time.time()
            return await self.call_groq(text)

    async def call_groq(self, text):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": f"Extract order JSON: {text}"}],
                        "response_format": {"type": "json_object"}
                    }
                )
                return json.loads(resp.json()['choices'][0]['message']['content']), "groq"
        except:
            return {"intent": "order", "items": [{"name": text, "qty": 1}]}, "fallback"

ai_service = AIService()
