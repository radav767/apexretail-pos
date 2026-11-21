"""Exact committed sale replay before mutable pricing/shift/license checks."""
import hashlib
import json
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Sale, SaleCommandReceipt, Device, Product
from app.financial_access import enforce_actor_branch
from app.subscriptions.write_policy import require_new_write

CREDENTIAL_FIELDS = {'device_key', 'discount_authorization_token', 'price_override_authorization_token', 'offline_shift_token', 'manager_authorization_token'}


def normalized(value):
    if isinstance(value, Decimal): return format(value.normalize(), 'f')
    if isinstance(value, UUID): return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None: raise HTTPException(422, 'Capture timestamps require a timezone')
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, dict): return {key: normalized(item) for key, item in value.items() if key not in CREDENTIAL_FIELDS}
    if isinstance(value, list): return [normalized(item) for item in value]
    return value


def fingerprint(data):
    body = data.model_dump(exclude=CREDENTIAL_FIELDS)
    return hashlib.sha256(json.dumps(normalized(body), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def actor_identity(actor, company_id):
    if actor is None: raise HTTPException(401, 'Authentication required')
    if actor.company_id != company_id: raise HTTPException(403, 'Forbidden')
    entity = actor.user if actor.actor_type == 'user' else actor.employee if actor.actor_type == 'employee' else None
    if entity is None or entity.company_id != company_id: raise HTTPException(403, 'Actor context required')
    if not entity.active or entity.deleted: raise HTTPException(401, 'Actor is no longer active')
    if actor.actor_type == 'user' and actor.role not in {'owner', 'administrator'}: raise HTTPException(403, 'Permission denied')
    if actor.actor_type == 'user' and entity.role not in {'owner', 'administrator'}: raise HTTPException(403, 'Permission denied')
    if actor.actor_type == 'user' and actor.authenticated_session_version is not None and actor.authenticated_session_version != entity.session_version:
        raise HTTPException(401, 'User session is no longer valid')
    if actor.actor_type == 'employee':
        version = actor.authenticated_session_version
        if version is not None and version != entity.session_version:
            raise HTTPException(401, 'Employee session is no longer valid')
        if actor.pos_session and (actor.pos_session.revoked_at or actor.pos_session.session_version != entity.session_version):
            raise HTTPException(401, 'Employee session is no longer valid')
    return entity.id


async def begin(db, data, actor):
    identity = actor_identity(actor, data.company_id)
    command_hash = fingerprint(data)
    if data.client_sale_id:
        # Existing sales identities are globally unique. Equal keys serialize
        # across tenants too, without exposing another tenant's receipt.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {'key': 'phase11-sale:' + str(data.client_sale_id)})
        receipt = await db.get(SaleCommandReceipt, data.client_sale_id)
        if receipt:
            if receipt.company_id != data.company_id: raise HTTPException(409, 'Client transaction identity is already in use')
            if receipt.actor_type != actor.actor_type or receipt.actor_id != identity: raise HTTPException(403, 'Original transaction belongs to another actor')
            if receipt.payload_hash != command_hash: raise HTTPException(409, 'Original transaction payload differs; retain for review')
            enforce_actor_branch(actor, receipt.branch_id)
            if actor.pos_session and actor.pos_session.device_id != receipt.device_id: raise HTTPException(403, 'Use the original register')
            if not receipt.device_id and data.device_key: raise HTTPException(403, 'Register context differs')
            if receipt.device_id:
                device = await db.get(Device, receipt.device_id)
                if (not device or device.company_id != data.company_id or not device.active or device.deleted
                        or device.removed_at or device.deactivated_at or device.branch_id != receipt.branch_id
                        or device.assignment_revision != receipt.assignment_revision):
                    raise HTTPException(403, 'Original register is no longer authorized')
                if data.device_key and device.device_key != data.device_key: raise HTTPException(403, 'Register identity mismatch')
                if actor.pos_session and actor.pos_session.device_id != device.id: raise HTTPException(403, 'Use the original register')
            sale = await db.get(Sale, receipt.sale_id)
            if sale is None or sale.company_id != data.company_id: raise HTTPException(409, 'Original receipt requires review')
            return sale, None
        existing = (await db.execute(select(Sale.id).where(Sale.client_sale_id == data.client_sale_id))).scalar_one_or_none()
        if existing:
            raise HTTPException(409, detail={'code': 'committed_sale_requires_lookup', 'message': 'Existing transaction has no complete replay proof. Retrieve the original receipt; do not resubmit with another identity.'})
    subscription = await require_new_write(db, data.company_id)
    if data.client_created_at and data.client_created_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(422, 'Queued transaction capture time is more than five minutes ahead')
    terms = subscription.commercial_terms
    if terms is not None:
        features = terms.get('features', {})
        if any(item.variant_id for item in data.items) and not features.get('variants', False): raise HTTPException(403, 'Subscription does not include variants')
        products = (await db.execute(select(Product.product_type).where(Product.company_id == data.company_id,
                    Product.id.in_([item.product_id for item in data.items])))).scalars().all()
        if any(kind in {'composite', 'bundle'} for kind in products) and not features.get('composites', False): raise HTTPException(403, 'Subscription does not include composites')
    return None, {'actor_id': identity, 'payload_hash': command_hash, 'actor_type': actor.actor_type}


def record(db, data, proof, sale, device):
    if data.client_sale_id:
        # Audited manager resolution may use historical register attribution.
        # Never invent its current assignment revision. Normal POS POST replay
        # then fails closed; the distinct manager-resolution receipt is exact.
        db.add(SaleCommandReceipt(client_sale_id=data.client_sale_id, company_id=data.company_id, sale_id=sale.id,
            branch_id=sale.branch_id, device_id=sale.device_id, assignment_revision=getattr(device, 'assignment_revision', None) if device else None, **proof))
