from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    get_auth_actor,
    ensure_company_access,
    require_billable_path_company,
    require_path_permission,
)
from app.business_settings.schema import (
    CompanyProfileOut,
    CompanyProfileUpdate,
    CompanySettingsOut,
    CompanySettingsUpdate,
    ReceiptSettingsOut,
    ReceiptSettingsUpdate,
    ShopSettingsOut,
    ShopSettingsUpdate,
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
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(actor, company_id)
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
    _actor: AuthActor = Depends(
        require_path_permission("business_settings_manage")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await BusinessSettingsService(db).update(company_id, data)


@router.get(
    "/company/{company_id}",
    response_model=CompanyProfileOut,
)
async def get_company_profile(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(
        require_path_permission("business_settings_manage")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await BusinessSettingsService(db).get_company_profile(
        company_id
    )


@router.patch(
    "/company/{company_id}",
    response_model=CompanyProfileOut,
)
async def update_company_profile(
    company_id: UUID,
    data: CompanyProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(
        require_path_permission("business_settings_manage")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await BusinessSettingsService(db).update_company_profile(
        company_id,
        data,
    )


@router.get(
    "/shops/{company_id}",
    response_model=list[ShopSettingsOut],
)
async def list_shop_settings(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(
        require_path_permission("business_settings_manage")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await BusinessSettingsService(db).list_shops(company_id)


@router.patch(
    "/shops/{company_id}/{shop_id}",
    response_model=ShopSettingsOut,
)
async def update_shop_settings(
    company_id: UUID,
    shop_id: UUID,
    data: ShopSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(
        require_path_permission("branches_manage")
    ),
):
    return await BusinessSettingsService(db).update_shop(
        company_id,
        shop_id,
        data,
    )


@router.get(
    "/receipts/{company_id}",
    response_model=ReceiptSettingsOut,
)
async def get_receipt_settings(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(
        require_path_permission("business_settings_manage")
    ),
):
    return await BusinessSettingsService(db).get_receipt_settings(
        company_id
    )


@router.patch(
    "/receipts/{company_id}",
    response_model=ReceiptSettingsOut,
)
async def update_receipt_settings(
    company_id: UUID,
    data: ReceiptSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(
        require_path_permission("business_settings_manage")
    ),
):
    return await BusinessSettingsService(db).update_receipt_settings(
        company_id,
        data,
    )
