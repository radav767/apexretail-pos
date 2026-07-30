from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_settings.schema import (
    CompanySettingsOut,
    CompanySettingsUpdate,
)
from app.business_settings.service import BusinessSettingsService
from app.db.session import get_db


router = APIRouter(prefix="/settings", tags=["Business Settings"])


@router.get(
    "/{company_id}",
    response_model=CompanySettingsOut,
)
async def get_company_settings(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await BusinessSettingsService(db).get(company_id)


@router.patch(
    "/{company_id}",
    response_model=CompanySettingsOut,
)
@router.put(
    "/{company_id}",
    response_model=CompanySettingsOut,
)
async def update_company_settings(
    company_id: UUID,
    data: CompanySettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await BusinessSettingsService(db).update(company_id, data)
