from app.inventory.stock_repository import BranchStockRepository
import hashlib
import json
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import AuditEvent, InventoryMovement


class TransferRepository:
    def __init__(self, db):
        self.db = db
        self.stock = BranchStockRepository(db)
        self.request_record = None

    async def prepare_request(self, data, actor=None):
        self.request_record = None
        if data.request_id is None:
            return None  # Legacy callers retain their original contract.
        payload = {"source_branch_id":str(data.source_branch_id),"destination_branch_id":str(data.destination_branch_id),
            "reference":(data.reference or "").strip(),"notes":(data.notes or "").strip(),
            "items":sorted([{"product_id":str(item.product_id),"quantity":format(item.quantity.normalize(),"f")}
                for item in data.items],key=lambda row:row["product_id"])}
        fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        identity = f"transfer:{data.company_id}:{data.request_id}"
        lock = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8],"big",signed=True)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":lock})
        receipt = (await self.db.execute(select(AuditEvent).where(AuditEvent.company_id==data.company_id,
            AuditEvent.action=="inventory_transfer_committed_v1",
            AuditEvent.details["request_id"].as_string()==str(data.request_id)))).scalar_one_or_none()
        if receipt:
            if receipt.details["payload_hash"] != fingerprint:
                raise HTTPException(409,"Transfer request identity reused with different values; original transfer retained")
            ids = [UUID(value) for value in receipt.details["movement_ids"]]
            rows = (await self.db.execute(select(InventoryMovement).where(
                InventoryMovement.company_id==data.company_id,InventoryMovement.id.in_(ids)))).scalars().all()
            if len(rows)!=len(ids):
                raise HTTPException(409,"Original transfer requires authorized reconciliation; do not resubmit")
            by_id={row.id:row for row in rows}
            return [by_id[value] for value in ids]
        self.request_record = AuditEvent(company_id=data.company_id,
            actor_employee_id=actor.employee.id if actor and actor.actor_type=="employee" else None,
            actor_user_id=actor.user.id if actor and actor.actor_type=="user" else None,
            device_id=actor.pos_session.device_id if actor and actor.pos_session else None,
            action="inventory_transfer_committed_v1",reason="Stock transfer",
            details={"request_id":str(data.request_id),"payload_hash":fingerprint,"request":payload})
        return None

    async def resolve_branch(
        self,
        company_id,
        branch_id,
    ):
        return await self.stock.resolve_branch(
            company_id,
            branch_id,
        )

    async def get_product(
        self,
        company_id,
        product_id,
    ):
        return await self.stock.get_product_for_update(
            company_id,
            product_id,
        )

    async def get_balance(
        self,
        company_id,
        branch,
        product,
    ):
        return await self.stock.get_balance_for_update(
            company_id,
            branch,
            product,
        )

    async def sync_product_total(self, product):
        return await self.stock.sync_product_total(product)

    async def save_transfer(
        self,
        products,
        balances,
        movements,
    ):
        try:
            self.db.add_all(products)
            self.db.add_all(balances)
            self.db.add_all(movements)

            from app.business_operations.batches import allocate_batch_movements
            await allocate_batch_movements(self.db, movements)
            if self.request_record is not None:
                self.request_record.details = {**self.request_record.details,"movement_ids":[str(m.id) for m in movements]}
                self.db.add(self.request_record)
            await self.db.commit()

            for movement in movements:
                await self.db.refresh(movement)

            return movements
        except Exception:
            await self.db.rollback()
            raise
