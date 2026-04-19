import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_chat():
    return client.chats.create(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
            temperature=0.4,
            system_instruction="""
You are SellMate AI.
You help shop owners take orders in Burmese.
Be short, clear, structured.
"""
        )
    )
