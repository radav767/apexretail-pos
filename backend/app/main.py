from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from app.subscriptions import router as subscriptions
from app.subscriptions.platform_router import platform, business as commercial_billing
from app.customers import router as customers
from app.credit import router as credit
from app.expenses import router as expenses
from app.currencies import router as currencies
from app.shifts import router as shifts
from app.printing.router import router as printing
from app.business_operations.router import router as operations
from app.fiscal.router import router as fiscal

app = FastAPI(title="ApexRetail POS API")


def serialize_validation_errors(errors: list[dict]) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []

    for error in errors:
        location = [
            str(part)
            for part in error.get("loc", [])
            if part not in {"body", "query", "path"}
        ]
        field = ".".join(location)
        message = str(error.get("msg", "Invalid value"))

        serialized.append(
            {
                "field": field,
                "message": message,
            }
        )

    return serialized


def error_payload(
    detail: str,
    *,
    field_errors: list[dict[str, str]] | None = None,
    code: str | None = None,
):
    payload = {
        "detail": detail,
        "message": detail,
    }

    if field_errors:
        payload["field_errors"] = field_errors

    if code:
        payload["code"] = code

    return payload

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pos.apexpos.cloud",
        "https://backoffice.apexpos.cloud",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
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
app.include_router(subscriptions.router, prefix="/api")
app.include_router(platform, prefix="/api")
app.include_router(commercial_billing, prefix="/api")
app.include_router(customers, prefix="/api")
app.include_router(credit, prefix="/api")
app.include_router(expenses, prefix="/api")
app.include_router(currencies, prefix="/api")
app.include_router(shifts, prefix="/api")
app.include_router(printing, prefix="/api")
app.include_router(operations, prefix="/api")
app.include_router(fiscal, prefix="/api")


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request,
    exc: RequestValidationError,
):
    field_errors = serialize_validation_errors(exc.errors())
    primary_error = field_errors[0] if field_errors else None

    if primary_error and primary_error["field"]:
        detail = (
            f"{primary_error['field']}: "
            f"{primary_error['message']}"
        )
    elif primary_error:
        detail = primary_error["message"]
    else:
        detail = "Request validation failed"

    return JSONResponse(
        status_code=422,
        content=error_payload(
            detail,
            field_errors=field_errors,
        ),
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(
    _request: Request,
    exc: HTTPException,
):
    if isinstance(exc.detail, dict):
        detail = str(exc.detail.get("message") or "Request failed")
        code = exc.detail.get("code")
        code = str(code) if code else None
    else:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        code = None

    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(detail, code=code),
        headers=exc.headers,
    )

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
