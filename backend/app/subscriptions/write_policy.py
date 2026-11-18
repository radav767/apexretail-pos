"""Pure current-license decisions; never bootstrap trials or commit a caller's work."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models import CompanySubscription


async def require_new_write(db, company_id, *, features=()):
    subscription = (await db.execute(select(CompanySubscription).where(
        CompanySubscription.company_id == company_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if subscription is None:
        raise HTTPException(402, detail={'code': 'subscription_unconfigured', 'message': 'Reconnect with a configured subscription. Retain pending transactions.'})
    now = datetime.now(timezone.utc)
    status = subscription.status
    end = subscription.trial_ends_at if status == 'trial' else subscription.current_period_ends_at or subscription.trial_ends_at
    if status in {'trial', 'active'} and end and now > end:
        status = 'grace_period' if subscription.grace_ends_at and now <= subscription.grace_ends_at else 'expired'
    if status == 'grace_period' and subscription.grace_ends_at and now > subscription.grace_ends_at:
        status = 'expired'
    if status not in {'trial', 'active', 'grace_period'}:
        raise HTTPException(402, detail={'code': 'subscription_write_restricted', 'message': 'Renew the subscription before posting new transactions. Retain pending transactions.'})
    terms = subscription.commercial_terms
    if terms is not None:
        for feature in features:
            if not terms.get('features', {}).get(feature, False):
                raise HTTPException(403, 'Subscription does not include ' + feature)
    return subscription
