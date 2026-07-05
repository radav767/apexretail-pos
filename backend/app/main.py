from fastapi import FastAPI

app = FastAPI(title="ApexRetail POS API")

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "app": "ApexRetail POS",
        "message": "ApexRetail POS API is running"
    }
