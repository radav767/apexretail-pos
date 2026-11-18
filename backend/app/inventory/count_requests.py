"""Append-only acknowledgements for stock counts, in the existing audit ledger."""
import hashlib
import json
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import AuditEvent, InventoryMovement
from .command_policy import context, audit_proof, verify_audit


async def prepare_count(db, data, actor):
    if data.request_id is None:
        return None, None
    payload = data.model_dump(mode="json")
    payload["items"] = sorted(payload["items"], key=lambda row:(row["product_id"],row.get("variant_id") or ""))
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    key=int.from_bytes(hashlib.sha256(f"count:{data.company_id}:{data.request_id}".encode()).digest()[:8],"big",signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":key})
    old=(await db.execute(select(AuditEvent).where(AuditEvent.company_id==data.company_id,
        AuditEvent.action=="inventory_count_committed_v1",AuditEvent.details["request_id"].as_string()==str(data.request_id)))).scalar_one_or_none()
    proof = await context(db, actor, data.company_id, data.branch_id)
    if old:
        verify_audit(old, proof)
        if old.details["payload_hash"]!=fingerprint:
            raise HTTPException(409,"Count request identity reused with different values")
        ids=[UUID(value) for value in old.details["movement_ids"]]
        rows=(await db.execute(select(InventoryMovement).where(InventoryMovement.company_id==data.company_id,
            InventoryMovement.id.in_(ids)))).scalars().all()
        if len(rows)!=len(ids):raise HTTPException(409,"Original count requires authorized reconciliation")
        indexed={row.id:row for row in rows}
        return [indexed[value] for value in ids],None
    event=AuditEvent(company_id=data.company_id,action="inventory_count_committed_v1",reason="Physical stock count",
        actor_employee_id=actor.employee.id if actor and actor.employee else None,
        actor_user_id=actor.user.id if actor and actor.user else None,
        device_id=actor.pos_session.device_id if actor and actor.pos_session else None,
        details={**audit_proof(proof), "request_id":str(data.request_id),"payload_hash":fingerprint,"request":payload})
    return None,event
