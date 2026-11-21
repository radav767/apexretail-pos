import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from app.employees.permissions import has_permission
from app.employees.manager_approval import consume_manager_authorization
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import AuditEvent, Branch, Category, Device, PrinterStation, PrinterRoute, PrintJob, Product, Sale, SaleItem


def digest(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def permit(actor, permission):
    if actor.actor_type == 'user' and actor.role not in {'owner', 'administrator'}:
        raise HTTPException(403, 'Permission denied')
    if actor.actor_type == "employee" and not has_permission(actor.permissions or {}, permission):
        raise HTTPException(403, "Permission denied")


class PrintingService:
    def __init__(self, db, actor):
        self.db, self.actor = db, actor

    def audit(self, action, **details):
        a = self.actor
        self.db.add(AuditEvent(company_id=a.company_id,
            actor_employee_id=a.employee.id if a.employee else None,
            actor_user_id=a.user.id if a.user else None,
            device_id=a.pos_session.device_id if a.pos_session else None,
            action=action, details=jsonable_encoder(details)))

    async def offline_review(self, sale_id, data):
        permit(self.actor, "sales_process")
        sale = await self.db.get(Sale, sale_id)
        if not sale or sale.company_id != self.actor.company_id:
            raise HTTPException(404, "Sale not found")
        enforce_actor_branch(self.actor, sale.branch_id)
        if self.actor.actor_type == "employee" and (
            not self.actor.pos_session or self.actor.pos_session.device_id != sale.device_id
            or sale.employee_id != self.actor.employee.id
        ):
            raise HTTPException(403, "Review belongs to the original cashier/register")
        self.audit("offline_print_reviewed", sale_id=sale.id, decision=data.decision, reason=data.reason)
        await self.db.commit()
        return {"reviewed": True}

    async def station(self, station_id, lock=False, management=False):
        query = select(PrinterStation).where(PrinterStation.id == station_id, PrinterStation.company_id == self.actor.company_id)
        if lock:
            query = query.with_for_update()
        row = (await self.db.execute(query)).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Printer station not found")
        enforce_actor_branch(self.actor, row.branch_id)
        if not management and self.actor.actor_type == "employee":
            if not self.actor.pos_session or self.actor.pos_session.device_id != row.device_id:
                raise HTTPException(403, "Use this station's assigned register")
        return row

    async def list_stations(self, company_id):
        enforce_actor_company(self.actor, company_id)
        q = select(PrinterStation).where(PrinterStation.company_id == company_id).order_by(PrinterStation.name)
        if self.actor.actor_type == "employee" and self.actor.role not in {"owner", "administrator"}:
            q = q.where(PrinterStation.branch_id == self.actor.employee.branch_id)
        rows = (await self.db.execute(q)).scalars().all()
        output = []
        for row in rows:
            routes = (await self.db.execute(select(PrinterRoute).where(PrinterRoute.station_id == row.id))).scalars().all()
            output.append({**{c.name: getattr(row, c.name) for c in row.__table__.columns},
                "routes": [{"target_type": r.target_type, "target_id": r.target_id} for r in routes]})
        return output

    async def save_station(self, data, station_id=None):
        permit(self.actor, "printers_manage")
        if data.purpose in {'kitchen','bar'}:
            from app.subscriptions.commercial import enforce_feature
            await enforce_feature(self.db,self.actor.company_id,'kitchen_printing')
        enforce_actor_branch(self.actor, data.branch_id)
        branch = await self.db.get(Branch, data.branch_id)
        device = await self.db.get(Device, data.device_id)
        if not branch or branch.company_id != self.actor.company_id or branch.shop_id != data.shop_id:
            raise HTTPException(400, "Invalid shop/branch assignment")
        if not device or device.company_id != self.actor.company_id or device.branch_id != branch.id or device.removed_at is not None:
            raise HTTPException(400, "Invalid register assignment")
        seen = set()
        for route in data.routes:
            target = await self.db.get(Product if route.target_type == "product" else Category, route.target_id)
            if not target or target.company_id != self.actor.company_id:
                raise HTTPException(400, "Routing target not found in this company")
            identity = (route.target_type, route.target_id)
            if identity in seen:
                raise HTTPException(400, "Duplicate printer route")
            seen.add(identity)
        row = await self.station(station_id, lock=True, management=True) if station_id else PrinterStation(company_id=self.actor.company_id)
        if station_id and any(getattr(row, k) != getattr(data, k) for k in ("shop_id", "branch_id", "device_id")):
            raise HTTPException(409, "Archive and create a station to change its register")
        # Lock prevents changing routing/config underneath an enqueue operation.
        for key, value in data.model_dump(exclude={"routes"}).items():
            setattr(row, key, value)
        self.db.add(row)
        await self.db.flush()
        await self.db.execute(delete(PrinterRoute).where(PrinterRoute.station_id == row.id))
        for route in data.routes:
            self.db.add(PrinterRoute(station_id=row.id, **route.model_dump()))
        self.audit("printer_station_saved", station_id=row.id)
        await self.db.commit()
        return {"id": row.id}

    async def enqueue(self, station_id, data):
        station = await self.station(station_id, lock=True)
        if station.purpose in {'kitchen','bar'}:
            from app.subscriptions.commercial import enforce_feature
            await enforce_feature(self.db,self.actor.company_id,'kitchen_printing')
        if not station.active:
            raise HTTPException(409, "Printer station is inactive")
        # Permission revocation applies to retries too, not just new inserts.
        if data.kind == "test":
            permit(self.actor, "printers_manage")
        elif not data.reprint:
            permit(self.actor, "sales_process")
        suffix = digest(data.request_key) if data.reprint or data.kind == "test" else "original"
        key = f"{data.kind}:{data.sale_id or 'test'}:{suffix}"
        existing = (await self.db.execute(select(PrintJob).where(PrintJob.station_id == station.id, PrintJob.request_key == key))).scalar_one_or_none()
        # Original has one identity per sale/station, independent of network retries.
        if existing:
            if existing.payload.get('payment_method') in {'split','split_refund'}:
                from app.workflows.core import WorkflowService
                await WorkflowService(self.db,self.actor).current_context(self.actor.company_id,station.branch_id)
            if self.actor.employee and not has_permission(self.actor.permissions or {}, "printers_manage") and existing.requested_employee_id != self.actor.employee.id:
                raise HTTPException(403, "Print job belongs to another employee")
            return self.job_out(existing)
        if data.kind == "test":
            permit(self.actor, "printers_manage")
            payload = {"title": "PRINTER TEST — NOT A SALE", "items": [], "created_at": datetime.now(timezone.utc).isoformat()}
        else:
            sale = await self.db.get(Sale, data.sale_id) if data.sale_id else None
            if not sale or sale.company_id != self.actor.company_id:
                raise HTTPException(404, "Sale not found")
            if sale.payment_method in {'split','split_refund'}:
                from app.workflows.core import WorkflowService
                await WorkflowService(self.db,self.actor).current_context(sale.company_id,sale.branch_id)
            enforce_actor_branch(self.actor, sale.branch_id)
            if sale.branch_id != station.branch_id or sale.shop_id != station.shop_id or sale.device_id != station.device_id:
                raise HTTPException(403, "Sale belongs to another register")
            if data.reprint:
                if self.actor.actor_type == "employee" and not has_permission(self.actor.permissions or {}, "sales_receipt_reprint"):
                    await consume_manager_authorization(self.db, self.actor, data.manager_authorization, "receipt_reprint", {"sale_id": str(sale.id), "station_id": str(station.id)})
            else:
                permit(self.actor, "sales_process")
                if self.actor.employee and sale.employee_id != self.actor.employee.id:
                    raise HTTPException(403, "Original printing belongs to the sale cashier")
            if data.kind == "kot" and (station.purpose == "receipt" or sale.status != "completed" or sale.original_sale_id):
                raise HTTPException(400, "Kitchen tickets require a completed original sale and kitchen/bar station")
            if data.kind == "kot":
                from app.models import CommerceOrder
                if (await self.db.execute(select(CommerceOrder.id).where(CommerceOrder.sale_id == sale.id))).first():
                    raise HTTPException(409, "Use the original open-order kitchen tickets; payment must not send preparation again")
            if data.kind == "receipt" and station.purpose != "receipt":
                raise HTTPException(400, "Use a receipt station")
            items = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.id))).scalars().all()
            if data.kind == "kot":
                routes = (await self.db.execute(select(PrinterRoute).where(PrinterRoute.station_id == station.id))).scalars().all()
                product_ids = {r.target_id for r in routes if r.target_type == "product"}
                category_ids = {r.target_id for r in routes if r.target_type == "category"}
                items = [i for i in items if i.product_id in product_ids or i.category_id_snapshot in category_ids]
                if not items:
                    raise HTTPException(409, "No items routed to this station")
            payload = {"title": "KITCHEN ORDER" if data.kind == "kot" else "SALES RECEIPT",
                "order_number": sale.receipt_number, "created_at": (sale.client_created_at or sale.created_at).isoformat(),
                "cashier_name": sale.cashier_name, "waiter": sale.cashier_name, "table": data.table, "notes": data.notes,
                "business_name": "", "shop_name": sale.shop_name_snapshot,
                "branch_name": sale.branch_name_snapshot, "reprint": data.reprint,
                "items": [{"product_id": str(i.product_id), "name": i.product_name + (f" ({i.variant_name_snapshot})" if i.variant_name_snapshot else ""),
                    "quantity": str(i.quantity), "selling_unit": i.selling_unit,
                    "unit_price": str(i.unit_price), "line_total": str(i.line_total),
                    "line_discount_amount": str(i.line_discount_amount) if i.line_discount_amount is not None else None,
                    "notes": data.item_notes.get(i.id, "")[:500]} for i in items]}
            if data.kind == "receipt":
                # Reuse authoritative receipt snapshot, never calculate money here.
                from app.models import Company
                company = await self.db.get(Company, sale.company_id)
                payload.update({"id": str(sale.id), "company_id": str(sale.company_id),
                    "business_name": company.name, "receipt_number": sale.receipt_number,
                    **{key: (getattr(sale, key) if isinstance(getattr(sale, key), (bool, str)) or getattr(sale, key) is None else str(getattr(sale, key))) for key in (
                        "subtotal_amount", "discount_amount", "sale_discount_amount", "tax_name", "tax_rate", "tax_amount", "tax_inclusive", "total_amount", "amount_received", "change_due", "payment_method", "base_currency_code", "payment_currency_code", "payment_amount_original", "tendered_amount_original", "change_amount_original", "exchange_rate_snapshot", "status")},
                    "receipt_footer": sale.receipt_footer_snapshot,
                    "is_duplicate": data.reprint})
                if sale.payment_method in {'split','split_refund'}:
                    from app.sales.split_receipts import snapshot
                    payload['split_accounting']=await snapshot(self.db,sale)
        # Printer settings are snapshotted, so editing a station cannot silently
        # redirect previously queued work to another piece of hardware.
        payload["printer"] = {k: getattr(station, k) for k in ("transport", "address", "paper_width", "name")}
        job = PrintJob(company_id=self.actor.company_id, station_id=station.id, sale_id=data.sale_id,
            requested_employee_id=self.actor.employee.id if self.actor.employee else None,
            request_key=key, kind=data.kind, payload=payload, payload_hash=digest(payload), status="pending", attempts=0)
        self.db.add(job)
        await self.db.flush()
        self.audit("print_job_queued", job_id=job.id, station_id=station.id, reprint=data.reprint)
        await self.db.commit()
        return self.job_out(job)

    @staticmethod
    def job_out(job):
        return {k: getattr(job, k) for k in ("id", "station_id", "sale_id", "kind", "payload", "payload_hash", "status", "attempts", "last_error", "created_at", "claimed_at", "completed_at")}

    async def list_jobs(self, station_id):
        manager = self.actor.role in {"owner", "administrator"} or has_permission(self.actor.permissions or {}, "printers_manage")
        await self.station(station_id, management=manager)
        if not manager:
            if not has_permission(self.actor.permissions or {}, "orders_send"):
                permit(self.actor, "sales_process")
        q = select(PrintJob).where(PrintJob.station_id == station_id)
        if not manager:
            q = q.where(PrintJob.requested_employee_id == self.actor.employee.id)
        rows = (await self.db.execute(q.order_by(PrintJob.created_at.desc()).limit(100))).scalars().all()
        return [self.job_out(j) for j in rows]

    async def job(self, job_id):
        job = (await self.db.execute(select(PrintJob).where(PrintJob.id == job_id, PrintJob.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not job:
            raise HTTPException(404, "Print job not found")
        await self.station(job.station_id)
        if self.actor.employee and not has_permission(self.actor.permissions or {}, "printers_manage") and job.requested_employee_id != self.actor.employee.id:
            raise HTTPException(403, "Print job belongs to another employee")
        permit(self.actor, "orders_send" if job.order_id else "sales_process" if job.kind != "test" else "printers_manage")
        if digest(job.payload) != job.payload_hash:
            raise HTTPException(409, "Print snapshot integrity failure")
        return job

    async def claim(self, job_id, data):
        job = await self.job(job_id)
        if job.status != "pending":
            raise HTTPException(409, "Job was already claimed; inspect status before retrying")
        if job.attempts >= 5:
            raise HTTPException(409, "Retry limit reached; inspect the printer")
        job.status, job.claim_hash = "sending", digest(data.token)
        job.claimed_at = datetime.now(timezone.utc)
        job.attempts += 1
        self.audit("print_job_claimed", job_id=job.id, attempt=job.attempts)
        await self.db.commit()
        return self.job_out(job)

    async def result(self, job_id, data):
        job = await self.job(job_id)
        if not job.claim_hash or not hmac.compare_digest(job.claim_hash, digest(data.token)):
            raise HTTPException(403, "Invalid print claim")
        target = data.outcome
        if job.status != "sending":
            if job.status == target:
                return self.job_out(job)
            raise HTTPException(409, "Delivery result has already been recorded")
        job.status, job.last_error = target, data.error or None
        if target == "submitted":
            job.completed_at = datetime.now(timezone.utc)
        self.audit("print_job_result", job_id=job.id, outcome=target)
        await self.db.commit()
        return self.job_out(job)

    async def retry(self, job_id, data):
        job = await self.job(job_id)
        if self.actor.actor_type == "employee" and not has_permission(self.actor.permissions or {}, "printers_manage"):
            await consume_manager_authorization(self.db, self.actor, data.manager_authorization, "print_retry", {"job_id": str(job.id)})
        if job.status not in {"sending", "uncertain"}:
            raise HTTPException(409, "Only uncertain delivery can be resolved for retry")
        # Never retry an in-progress native call. Broken clients must be left
        # at least 60 seconds before a manager may acknowledge duplicate risk.
        if job.claimed_at and (datetime.now(timezone.utc) - job.claimed_at).total_seconds() < 60:
            raise HTTPException(409, "Wait for the current printer attempt to finish")
        job.status, job.claim_hash = "pending", None
        self.audit("print_retry_authorized", job_id=job.id, reason=data.reason, duplicate_risk_acknowledged=True)
        await self.db.commit()
        return self.job_out(job)
