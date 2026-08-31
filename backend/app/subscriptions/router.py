from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    ensure_company_access,
    get_auth_actor,
    require_body_owner,
    require_path_owner,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.subscriptions.schema import (
    SubscriptionActivateOut,
    SubscriptionActivateRequest,
    SubscriptionPageOut,
    SubscriptionWebhookIn,
    SubscriptionWebhookOut,
)
from app.subscriptions.service import SubscriptionService


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def get_service(
    db: AsyncSession = Depends(get_db),
) -> SubscriptionService:
    settings = get_settings()
    return SubscriptionService(
        db,
        offline_grace_hours=settings.subscription_offline_grace_hours,
        provider_name=settings.subscription_provider_name,
        checkout_base_url=settings.subscription_provider_checkout_base_url,
        webhook_secret=settings.subscription_provider_webhook_secret,
        webhook_signature_header=settings.subscription_webhook_signature_header,
        paynow_integration_id=settings.paynow_integration_id,
        paynow_integration_key=settings.paynow_integration_key,
        paynow_return_url=settings.paynow_return_url,
        paynow_result_url=settings.paynow_result_url,
    )


@router.get("/{company_id}", response_model=SubscriptionPageOut)
async def get_subscription_page(
    company_id: UUID,
    service: SubscriptionService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(actor, company_id)
    return await service.page(company_id)


@router.post("/activate", response_model=SubscriptionActivateOut)
async def activate_subscription(
    data: SubscriptionActivateRequest,
    service: SubscriptionService = Depends(get_service),
    _actor: AuthActor = Depends(require_body_owner),
):
    return await service.activate_or_renew(data.company_id, data.plan)


@router.post("/webhooks", response_model=SubscriptionWebhookOut)
async def process_subscription_webhook(
    request: Request,
    data: SubscriptionWebhookIn,
    service: SubscriptionService = Depends(get_service),
):
    body = await request.body()
    signature = request.headers.get(
        get_settings().subscription_webhook_signature_header
    )
    service.verify_webhook_signature(
        body=body,
        provided_signature=signature,
    )
    return await service.record_webhook(data)


@router.post("/paynow/result", response_model=SubscriptionWebhookOut)
async def process_paynow_result(
    request: Request,
    service: SubscriptionService = Depends(get_service),
):
    body = await request.body()
    return await service.process_paynow_result(body)
