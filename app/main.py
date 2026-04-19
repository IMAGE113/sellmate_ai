from fastapi import FastAPI

app = FastAPI(title="SellMate AI")

@app.get("/")
async def root():
    return {"message": "SellMate AI is live"}

@app.get("/health")
async def health():
    return {"status": "ok"}
