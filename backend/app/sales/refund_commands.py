from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Device, RefundCommandReceipt, Sale
from app.financial_access import enforce_actor_branch
from app.subscriptions.write_policy import require_new_write
from .commands import actor_identity, fingerprint


async def begin(db, data, actor):
    identity = actor_identity(actor, data.company_id)
    command_hash = fingerprint(data)
    if data.request_id:
        # Shared with sale client IDs: refunds also use the existing historical
        # by-client lookup. Never let a purpose/key collision become a sale.
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                         {'key':'phase11-sale:'+str(data.request_id)})
        receipt = await db.get(RefundCommandReceipt, data.request_id)
        if receipt:
            if receipt.company_id != data.company_id: raise HTTPException(409, 'Transaction identity is already in use')
            if receipt.actor_type != actor.actor_type or receipt.actor_id != identity:
                raise HTTPException(403, 'Original refund belongs to another actor')
            if receipt.payload_hash != command_hash: raise HTTPException(409, 'Refund command identity has different values')
            enforce_actor_branch(actor, receipt.branch_id)
            if actor.pos_session and actor.pos_session.device_id != receipt.device_id:
                raise HTTPException(403, 'Use the original refund register')
            if receipt.device_id:
                device = await db.get(Device, receipt.device_id)
                if (not device or device.company_id != data.company_id or not device.active or device.deleted or
                        device.removed_at or device.deactivated_at or device.branch_id != receipt.branch_id or
                        device.assignment_revision != receipt.assignment_revision):
                    raise HTTPException(403, 'Original refund register is no longer authorized')
                if data.device_key and device.device_key != data.device_key:
                    raise HTTPException(403, 'Register identity mismatch')
            result = await db.get(Sale, receipt.sale_id)
            if not result or result.company_id != data.company_id or result.original_sale_id != data.original_sale_id:
                raise HTTPException(409, 'Original refund requires review')
            return result, None
        if (await db.execute(select(Sale.id).where(Sale.client_sale_id == data.request_id))).first():
            raise HTTPException(409, 'Transaction identity is already recorded; retrieve the original receipt')
    await require_new_write(db, data.company_id)
    return None, {'actor_type':actor.actor_type, 'actor_id':identity, 'payload_hash':command_hash}


def record(db, data, proof, refund, device):
    if data.request_id:
        db.add(RefundCommandReceipt(request_id=data.request_id, company_id=data.company_id, sale_id=refund.id,
            branch_id=refund.branch_id, device_id=refund.device_id,
            assignment_revision=device.assignment_revision if device else None, **proof))
