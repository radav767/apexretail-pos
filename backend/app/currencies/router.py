from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import AuthActor, require_body_permission, require_path_permission
from app.currencies.repository import CurrencyRepository
from app.currencies.schema import CurrencyCreate, CurrencyOut, CurrencyUpdate, ExchangeRateCreate, ExchangeRateOut, ExchangeRatePage, MultiCurrencyUpdate, PosCurrencyConfigOut
from app.currencies.service import CurrencyService
from app.db.session import get_db


router = APIRouter(prefix="/currencies", tags=["Currencies"])


def get_service(db=Depends(get_db)):
    return CurrencyService(CurrencyRepository(db))


@router.get("/{company_id}", response_model=list[CurrencyOut])
async def list_currencies(company_id: UUID, active: bool | None = None, at: datetime | None = None, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("currencies_manage"))):
    return await service.list(company_id, actor, active=active, at=at)


@router.get("/{company_id}/pos-config", response_model=PosCurrencyConfigOut)
async def pos_currency_config(company_id: UUID, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("sales"))):
    return await service.pos_config(company_id, actor)


@router.post("", response_model=CurrencyOut)
async def create_currency(data: CurrencyCreate, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("currencies_manage"))):
    return await service.create(data, actor)


@router.patch("/configuration/{company_id}", response_model=PosCurrencyConfigOut)
async def update_currency_configuration(company_id: UUID, data: MultiCurrencyUpdate, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("currencies_manage"))):
    return await service.set_multi_currency(company_id, data.enabled, actor)


@router.patch("/{company_id}/{currency_id}", response_model=CurrencyOut)
async def update_currency(company_id: UUID, currency_id: UUID, data: CurrencyUpdate, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("currencies_manage"))):
    return await service.update(company_id, currency_id, data, actor)


@router.post("/{company_id}/{currency_id}/set-base", response_model=CurrencyOut)
async def set_base_currency(company_id: UUID, currency_id: UUID, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("currencies_manage"))):
    return await service.set_base(company_id, currency_id, actor)


@router.get("/{company_id}/rates/history", response_model=ExchangeRatePage | list[ExchangeRateOut])
async def rate_history(company_id: UUID, currency_id: UUID | None = None, page: int | None = Query(None, ge=1), page_size: int = Query(25, ge=1, le=100), limit: int = Query(100, ge=1, le=500), service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("currencies_manage"))):
    if page is None:
        items, _ = await service.rates(company_id, actor, currency_id=currency_id, limit=limit, offset=0)
        return items
    items, total = await service.rates(company_id, actor, currency_id=currency_id, limit=page_size, offset=(page - 1) * page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": ceil(total / page_size) if total else 0}


@router.get("/{company_id}/rates/current", response_model=list[CurrencyOut])
async def current_rates(company_id: UUID, at: datetime | None = None, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("currencies_manage"))):
    return await service.list(company_id, actor, active=True, at=at)


@router.post("/rates", response_model=ExchangeRateOut)
async def create_rate(data: ExchangeRateCreate, service: CurrencyService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("currencies_manage"))):
    return await service.create_rate(data, actor)
