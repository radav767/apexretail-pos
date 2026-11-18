"""Durable request proof for new expenses and credit collections."""
from fastapi import HTTPException
from sqlalchemy import text
from app.models import Device
from app.sales.commands import actor_identity, fingerprint


async def lock_command(db, kind, data, actor):
    actor_identity(actor, data.company_id)
    # Normalize before lookup, hashing and persistence, including whitespace.
    data.idempotency_key = data.idempotency_key.strip()
    if len(data.idempotency_key) < 8:
        raise HTTPException(422, 'Command identity must contain at least eight non-padding characters')
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                     {'key': f'phase11-finance:{kind}:{data.company_id}:{data.idempotency_key}'})
    return fingerprint(data)


async def verify_replay(db, existing, data, actor, command_hash):
    if not existing.command_hash:
        raise HTTPException(409, 'Historical command has no complete request proof; retrieve the original record')
    if (existing.command_actor_type != actor.actor_type or
            existing.command_actor_id != actor_identity(actor, data.company_id)):
        raise HTTPException(403, 'Original command belongs to another actor')
    if existing.command_hash != command_hash:
        raise HTTPException(409, 'Command identity was used for a different request')
    if actor.pos_session and actor.pos_session.device_id != existing.device_id:
        raise HTTPException(403, 'Use the original register')
    if existing.device_id:
        device = await db.get(Device, existing.device_id)
        if (not device or device.company_id != data.company_id or not device.active or device.deleted or
                device.removed_at or device.deactivated_at or device.branch_id != existing.branch_id or
                device.assignment_revision != existing.command_device_revision):
            raise HTTPException(403, 'Original register is no longer authorized')


async def stamp(db, row, actor, command_hash):
    row.command_hash = command_hash
    row.command_actor_type = actor.actor_type
    row.command_actor_id = actor_identity(actor, row.company_id)
    if row.device_id:
        device = await db.get(Device, row.device_id)
        if not device or device.company_id != row.company_id:
            raise HTTPException(403, 'Register context required')
        row.command_device_revision = device.assignment_revision
