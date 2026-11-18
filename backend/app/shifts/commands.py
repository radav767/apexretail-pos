from fastapi import HTTPException
from sqlalchemy import select
from app.models import CashierShift, ShiftCommandReceipt
from app.inventory.command_policy import context, lock_request, verify_row
from app.sales.commands import fingerprint
from app.subscriptions.write_policy import require_new_write


async def begin(db, data, actor, kind, shift=None):
    key = data.idempotency_key.strip()
    if len(key) < 8: raise HTTPException(422, 'Command identity requires eight non-padding characters')
    branch_id = shift.branch_id if shift else actor.pos_session.branch_id if actor.pos_session else None
    proof = await context(db, actor, actor.company_id, branch_id)
    # Opening locks its key before looking for an open shift. Other commands
    # already hold their one target shift lock; no code acquires another shift
    # while holding the shared key. Manager resolution holds sale identity first.
    await lock_request(db, 'shift-closing' if kind in {'close','manager_close'} else 'shift-'+kind, actor.company_id, key)
    command_hash = fingerprint(data.model_copy(update={'idempotency_key':key}))
    old = await db.get(ShiftCommandReceipt, (actor.company_id, kind, key))
    if old:
        verify_row(old, proof)
        if old.payload_hash != command_hash or shift and old.shift_id != shift.id:
            raise HTTPException(409, 'Shift command identity was used for a different request')
        result = await db.get(CashierShift, old.shift_id)
        if not result or result.company_id != actor.company_id: raise HTTPException(409, 'Original shift requires review')
        return old, None
    if kind in {'close', 'manager_close'}:
        occupied = (await db.execute(select(CashierShift.id).where(CashierShift.company_id == actor.company_id,
            CashierShift.close_idempotency_key == key))).scalar_one_or_none()
        if occupied is not None and occupied != shift.id:
            raise HTTPException(409, 'Closure command identity belongs to another shift')
    if kind in {'open','cash'} or kind == 'resolution' and data.action == 'post_to_original_shift':
        await require_new_write(db, actor.company_id)
    return None, {**proof, 'company_id':actor.company_id, 'kind':kind, 'command_key':key, 'payload_hash':command_hash}


def receipt(proof, shift_id, *, movement_id=None, resolution_id=None):
    return ShiftCommandReceipt(**proof, shift_id=shift_id, movement_id=movement_id, resolution_id=resolution_id)
