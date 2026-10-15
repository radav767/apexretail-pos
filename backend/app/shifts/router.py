import csv
import io
import json
from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response

from app.auth.dependencies import AuthActor, get_auth_actor, require_path_permission
from app.db.session import get_db
from app.shifts.repository import ShiftRepository
from app.shifts.report import simple_pdf, thermal_html
from app.shifts.schema import (
    CashMovementCreate, CashMovementOut, OfflineSaleResolutionCreate,
    OfflineSaleResolutionOut, OfflineSaleResolutionPage, ShiftClose,
    ShiftFilterOptions, ShiftOpen, ShiftOut, ShiftPage,
)
from app.shifts.service import ShiftService


router = APIRouter(prefix="/shifts", tags=["Cashier Shifts"])


def _csv_text(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def get_service(db=Depends(get_db)):
    return ShiftService(ShiftRepository(db))


@router.post("/open", response_model=ShiftOut)
async def open_shift(data: ShiftOpen, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.open(data, actor)


@router.get("/current", response_model=ShiftOut | None)
async def current_shift(service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.current(actor)


@router.get("/current/close-preview", response_model=ShiftOut)
async def close_preview(service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.preview_close(actor)


@router.post("/current/cash-movements", response_model=CashMovementOut)
async def create_current_cash_movement(data: CashMovementCreate, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.add_movement(data, actor)


@router.get("/my-history", response_model=ShiftPage)
async def my_shift_history(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
    service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor),
):
    items, total = await service.my_history(actor, page=page, page_size=page_size)
    return {
        "items": items, "page": page, "page_size": page_size,
        "total": total, "total_pages": ceil(total / page_size) if total else 0,
    }


@router.get("/mine/{shift_id}", response_model=ShiftOut)
async def my_shift_detail(shift_id: UUID, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.my_detail(shift_id, actor)


@router.post("/{shift_id}/close", response_model=ShiftOut)
async def close_shift(shift_id: UUID, data: ShiftClose, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.close(shift_id, data, actor)


@router.post("/{shift_id}/cash-movements", response_model=CashMovementOut)
async def create_cash_movement(shift_id: UUID, data: CashMovementCreate, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.create_cash_movement(shift_id, data, actor)


@router.post("/offline-resolutions", response_model=OfflineSaleResolutionOut)
async def resolve_offline_sale(data: OfflineSaleResolutionCreate, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.resolve_offline_sale(data, actor)


@router.get("/offline-resolutions/company/{company_id}", response_model=OfflineSaleResolutionPage)
async def offline_resolution_history(
    company_id: UUID,
    action: str | None = Query(default=None, pattern="^(post_to_original_shift|retain_quarantined)$"),
    shift_id: UUID | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor),
):
    items, total = await service.offline_resolution_history(
        company_id, actor, action=action, shift_id=shift_id,
        limit=page_size, offset=(page - 1) * page_size,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": ceil(total / page_size) if total else 0}


@router.post("/{shift_id}/manager-close", response_model=ShiftOut)
async def manager_close_shift(shift_id: UUID, data: ShiftClose, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.manager_close(shift_id, data, actor)


@router.get("/{shift_id}/manager-close-preview", response_model=ShiftOut)
async def manager_close_preview(shift_id: UUID, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.manager_preview_close(shift_id, actor)


@router.get("/{shift_id}/z-report", response_model=ShiftOut)
async def z_report(shift_id: UUID, reprint: bool = False, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.z_report(shift_id, actor, reprint=reprint)


@router.get("/{shift_id}/z-report/thermal", response_class=HTMLResponse)
async def z_report_thermal(
    shift_id: UUID, paper_width: str = Query("80mm", pattern="^(58mm|80mm)$"),
    reprint: bool = False, service: ShiftService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    report = await service.z_report(shift_id, actor, reprint=reprint)
    return HTMLResponse(thermal_html(report, paper_width))


@router.get("/{shift_id}/z-report.pdf")
async def z_report_pdf(shift_id: UUID, reprint: bool = False, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    report = await service.z_report(shift_id, actor, reprint=reprint)
    return Response(
        simple_pdf(report), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report["shift_number"]}.pdf"'},
    )


@router.get("/company/{company_id}/filters", response_model=ShiftFilterOptions)
async def shift_filter_options(company_id: UUID, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("reports"))):
    return await service.filter_options(company_id, actor)


@router.get("/company/{company_id}/export.csv")
async def export_shift_history(
    company_id: UUID,
    branch_id: UUID | None = None,
    employee_id: UUID | None = None,
    device_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    service: ShiftService = Depends(get_service),
    actor: AuthActor = Depends(require_path_permission("reports")),
):
    filters = {
        "branch_id": branch_id, "employee_id": employee_id, "device_id": device_id,
        "status": status, "start_at": start_at, "end_at": end_at,
    }
    rows, _ = await service.export_history(company_id, actor, **filters)
    report_summary = await service.report_summary(company_id, actor, **filters)
    output = io.StringIO(newline="")
    fields = (
        "shift_number", "shift_id", "cashier", "cashier_id", "shop", "branch",
        "register", "status", "opened_at", "closed_at", "base_currency",
        "gross_sales_base", "net_sales_base", "cost_of_sales_base",
        "gross_profit_base", "discounts_base", "cash_sales_base",
        "card_sales_base", "mobile_sales_base", "credit_sales_base",
        "cash_settlements_base", "card_settlements_base", "mobile_settlements_base",
        "cash_expenses_base", "noncash_expenses_base", "currency_cash_breakdown",
    )
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        summary = row["summary"]
        writer.writerow({
            "shift_number": _csv_text(row["shift_number"]), "shift_id": row["id"],
            "cashier": _csv_text(row.get("cashier_name") or "Unknown"),
            "cashier_id": row["employee_id"], "shop": _csv_text(row.get("shop_name") or "Unknown"),
            "branch": _csv_text(row.get("branch_name") or "Unknown"),
            "register": _csv_text(row.get("register_name") or "Unknown"), "status": row["status"],
            "opened_at": row["opened_at"], "closed_at": row["closed_at"],
            "base_currency": report_summary.get("base_currency_code"),
            "gross_sales_base": summary.get("gross_sales_base"),
            "net_sales_base": summary.get("net_sales_base"),
            "cost_of_sales_base": summary.get("cost_of_sales_base"),
            "gross_profit_base": summary.get("gross_profit_base"),
            "discounts_base": summary.get("discounts_base"),
            "cash_sales_base": summary.get("cash_sales_base"),
            "card_sales_base": summary.get("card_sales_base"),
            "mobile_sales_base": summary.get("mobile_sales_base"),
            "credit_sales_base": summary.get("credit_sales_base"),
            "cash_settlements_base": summary.get("cash_settlements_base"),
            "card_settlements_base": summary.get("card_settlements_base"),
            "mobile_settlements_base": summary.get("mobile_settlements_base"),
            "cash_expenses_base": summary.get("cash_expenses_base"),
            "noncash_expenses_base": summary.get("noncash_expenses_base"),
            "currency_cash_breakdown": json.dumps(row["currencies"], default=str),
        })
    return Response(
        output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="shift-report-{company_id}.csv"'},
    )


@router.get("/company/{company_id}/{shift_id}", response_model=ShiftOut)
async def shift_detail(company_id: UUID, shift_id: UUID, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("reports"))):
    return await service.detail(company_id, shift_id, actor)


@router.get("/company/{company_id}", response_model=ShiftPage)
async def shift_history(company_id: UUID, branch_id: UUID | None = None, employee_id: UUID | None = None, device_id: UUID | None = None, status: str | None = Query(default=None, pattern="^(open|closed)$"), start_at: datetime | None = None, end_at: datetime | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), service: ShiftService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("reports"))):
    filters = {
        "branch_id": branch_id, "employee_id": employee_id, "device_id": device_id,
        "status": status, "start_at": start_at, "end_at": end_at,
    }
    items, total = await service.history(
        company_id, actor, **filters, limit=page_size, offset=(page - 1) * page_size,
    )
    summary = await service.report_summary(company_id, actor, **filters)
    return {
        "items": items, "page": page, "page_size": page_size,
        "total": total, "total_pages": ceil(total / page_size) if total else 0,
        "summary": summary,
    }
