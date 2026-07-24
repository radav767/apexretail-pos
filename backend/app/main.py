from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth import router as auth
from app.products import router as products
from app.sales import router as sales
from app.dashboard import router as dashboard
from app.inventory import router as inventory
from app.inventory import branch_router
from app.inventory import transfer_router
from app.devices import router as devices

app = FastAPI(title="ApexRetail POS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pos.apexpos.cloud",
        "https://backoffice.apexpos.cloud",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(branch_router.router, prefix="/api")
app.include_router(transfer_router.router, prefix="/api")
app.include_router(devices.router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"ok": True, "app": "ApexRetail POS"}
