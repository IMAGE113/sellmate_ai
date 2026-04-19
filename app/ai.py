from google import genai
from google.genai import types
import os

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_KEY)


SYSTEM_PROMPT = """
You are SellMate AI.
You are business order assistant for Myanmar merchants.
Be short, clear, actionable.
"""


def get_gemini_chat():
    return client.chats.create(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4
        )
    )
