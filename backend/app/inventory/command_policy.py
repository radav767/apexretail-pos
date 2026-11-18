"""Current stock authority and original-command actor/register bindings."""
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Device
from app.sales.commands import actor_identity
from app.financial_access import enforce_actor_branch
from app.printing.service import permit
from app.subscriptions.write_policy import require_new_write


async def context(db, actor, company_id, branch_id):
    identity = actor_identity(actor, company_id)
    if branch_id is not None: enforce_actor_branch(actor, branch_id)
    device = None
    if actor.pos_session:
        session = actor.pos_session
        device = (await db.execute(select(Device).where(Device.id == session.device_id)
                                  .execution_options(populate_existing=True))).scalar_one_or_none()
        if (not device or device.company_id != company_id or not device.active or device.deleted or
                device.removed_at or device.deactivated_at or device.branch_id != session.branch_id or
                branch_id is not None and device.branch_id != branch_id):
            raise HTTPException(403, 'Register is no longer authorized for this stock operation')
    return {'actor_type':actor.actor_type, 'actor_id':identity,
            'device_id':device.id if device else None, 'assignment_revision':device.assignment_revision if device else None}


async def authorize(db, data, actor, permission=None, *, new=False):
    if actor and actor.employee and data.branch_id is None:
        data.branch_id = actor.employee.branch_id
    proof = await context(db, actor, data.company_id, data.branch_id)
    if permission: permit(actor, permission)
    if new:
        items = getattr(data, 'items', [data])
        await require_new_write(db, data.company_id, features=('variants',) if any(getattr(row, 'variant_id', None) for row in items) else ())
    return proof


async def lock_request(db, kind, company, request):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                     {'key':f'phase11-stock:{kind}:{company}:{request}'})


def audit_proof(proof):
    return {'command_version':2, 'command_actor_type':proof['actor_type'],
            'command_actor_id':str(proof['actor_id']), 'command_device_revision':proof['assignment_revision']}


def verify_audit(receipt, proof):
    if receipt.details.get('command_version') != 2:
        raise HTTPException(409, 'Historical stock command has no complete actor/register proof; retrieve original movements')
    if (receipt.details.get('command_actor_type') != proof['actor_type'] or
            receipt.details.get('command_actor_id') != str(proof['actor_id']) or
            receipt.device_id != proof['device_id'] or
            receipt.details.get('command_device_revision') != proof['assignment_revision']):
        raise HTTPException(403, 'Original stock command belongs to another actor or register assignment')


def verify_row(receipt, proof):
    if not receipt.actor_type or not receipt.actor_id:
        raise HTTPException(409, 'Historical stock command has no complete actor/register proof; retrieve original movements')
    if any(getattr(receipt, field) != value for field,value in proof.items()):
        raise HTTPException(403, 'Original stock command belongs to another actor or register assignment')
