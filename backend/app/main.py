from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth

app = FastAPI(title="ApexRetail POS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pos.apexpos.cloud",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"ok": True, "app": "ApexRetail POS"}
