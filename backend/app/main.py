from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth import router as auth
from app.products import router as products
from app.dashboard import router as dashboard
from app.inventory import router as inventory
from app.inventory import branch_router
from app.inventory import transfer_router
from app.devices import router as devices
from app.employees import router as employees
from app.reports import router as reports
from app.business_settings import router as business_settings

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
app.include_router(dashboard.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(branch_router.router, prefix="/api")
app.include_router(transfer_router.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(reports, prefix="/api")
app.include_router(business_settings.router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"ok": True, "app": "ApexRetail POS"}

# Register sales routes after the FastAPI application is fully created.
# This avoids partial-router registration caused by import ordering.
from app.sales.router import router as sales_router

app.include_router(
    sales_router,
    prefix="/api",
)

