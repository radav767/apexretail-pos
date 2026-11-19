import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func, or_, text
from app.financial_access import enforce_actor_branch
from app.employees.permissions import has_permission
from app.models import (Company, BusinessProfile, Branch, Device, Employee, Customer, Product, ProductVariant,
    DiningTable, HospitalityRoom, GuestAccount, CommerceOrder, CommerceOrderItem, KitchenTicket, PrintJob, PrinterStation, PrinterRoute,
    Sale, CreditReceivable, ProductBatch, InventoryBalance)
from app.printing.service import PrintingService, permit, digest
from .profiles import PROFILES, infer_profile


def row_dict(row, fields):
    return {key: getattr(row, key) for key in fields}


class BusinessService(PrintingService):
    async def require_write(self, *features):
        from app.subscriptions.write_policy import require_new_write
        await require_new_write(self.db, self.actor.company_id, features=features)

    async def commit_operation(self):
        await self.db.commit()

    async def profile(self):
        company = await self.db.get(Company, self.actor.company_id)
        if not company: raise HTTPException(404, "Company not found")
        profile = await self.db.get(BusinessProfile, company.id)
        from app.models import TipSettings
        tips = await self.db.get(TipSettings, company.id)
        # Existing Settings/registration remain authoritative for the label.
        key = infer_profile(company.business_type)
        features = set(PROFILES[key]["features"])
        # A profile change must not strand existing work. Permissions and all
        # branch checks still apply on every read/write route.
        for kind, feature in (("restaurant", "restaurant"), ("room_service", "hospitality"), ("quotation", "wholesale")):
            query = select(CommerceOrder.id).where(CommerceOrder.company_id == company.id, CommerceOrder.kind == kind)
            if self.actor.employee: query = query.where(CommerceOrder.branch_id == self.actor.employee.branch_id)
            if (await self.db.execute(query.limit(1))).first(): features.add(feature)
        batch_query = select(ProductBatch.id).where(ProductBatch.company_id == company.id)
        if self.actor.employee: batch_query = batch_query.where(ProductBatch.branch_id == self.actor.employee.branch_id)
        if (await self.db.execute(batch_query.limit(1))).first(): features.add("pharmacy")
        if "hospitality" in features: features.add("restaurant")
        from app.subscriptions.commercial import terms_for
        licensed=await terms_for(self.db,self.actor.company_id)
        if licensed is not None:features={f for f in features if licensed.get('features',{}).get(f,False)}
        return {"profile": key, "name": PROFILES[key]["name"], "features": sorted(features),
            "employee_id": self.actor.employee.id if self.actor.employee else None,
            "tips_enabled": bool(tips and tips.enabled),
            "separate_tips": tips is not None,
            "legacy_business_type": company.business_type, "tip_product_id": profile.tip_product_id if profile else None,
            "service_product_id": profile.service_product_id if profile else None,
            "permissions": self.actor.permissions or {}, "administrator": self.actor.role in {"owner", "administrator"} or self.actor.role in {"owner", "administrator"}}

    async def feature(self, name):
        from app.subscriptions.commercial import enforce_feature
        await enforce_feature(self.db,self.actor.company_id,name)
        if name not in (await self.profile())["features"]:
            raise HTTPException(409, "Enable the appropriate business profile in Settings first")

    async def save_profile(self, data):
        await self.require_write()
        permit(self.actor, "business_settings_manage")
        for product_id in (data.tip_product_id, data.service_product_id):
            if product_id:
                product = await self.db.get(Product, product_id)
                if not product or product.company_id != self.actor.company_id or product.deleted or not product.active or product.track_inventory or product.product_type not in {"service", "non_stock"}:
                    raise HTTPException(400, "Charges require an active non-stock/service product with reviewed tax settings")
        profile = await self.db.get(BusinessProfile, self.actor.company_id)
        if not profile: profile = BusinessProfile(company_id=self.actor.company_id)
        for key, value in data.model_dump().items(): setattr(profile, key, value)
        self.db.add(profile)
        company = await self.db.get(Company, self.actor.company_id)
        company.business_type = PROFILES[data.profile]["name"]
        self.audit("business_profile_changed", profile=data.profile)
        await self.db.commit()
        return await self.profile()

    async def branch(self, branch_id):
        branch = await self.db.get(Branch, branch_id)
        if not branch or branch.company_id != self.actor.company_id: raise HTTPException(404, "Branch not found")
        enforce_actor_branch(self.actor, branch.id)
        return branch

    async def options(self):
        # No PINs, device secrets, cost prices or customer financial balances.
        if self.actor.actor_type == "employee" and not any(has_permission(self.actor.permissions or {}, p) for p in ("orders_manage", "orders_settle", "restaurant_manage", "hospitality_manage", "batches_manage", "batches_view", "quotations_manage", "business_settings_manage")):
            raise HTTPException(403, "Permission denied")
        output = {}
        for key, model, fields in (("branches", Branch, ("id", "name", "shop_id")), ("devices", Device, ("id", "name", "branch_id")),
            ("products", Product, ("id", "name", "selling_price", "unit", "product_type")), ("variants", ProductVariant, ("id", "product_id", "name", "selling_price")),
            ("staff", Employee, ("id", "name", "branch_id", "role")), ("customers", Customer, ("id", "name"))):
            q = select(model).where(model.company_id == self.actor.company_id)
            if hasattr(model, "active"): q = q.where(model.active == True)
            if hasattr(model, "deleted"): q = q.where(model.deleted == False)
            if model == Device: q = q.where(Device.removed_at.is_(None), Device.deactivated_at.is_(None))
            if self.actor.actor_type == "employee" and self.actor.role not in {"owner", "administrator"}:
                if model == Branch: q = q.where(model.id == self.actor.employee.branch_id)
                elif hasattr(model, "branch_id"): q = q.where(model.branch_id == self.actor.employee.branch_id)
            rows = (await self.db.execute(q.limit(1000))).scalars().all()
            output[key] = [row_dict(row, fields) for row in rows]
        return output

    async def tables(self):
        permit(self.actor, "orders_manage" if not self.manager() else "restaurant_manage")
        q = select(DiningTable).where(DiningTable.company_id == self.actor.company_id)
        if self.actor.actor_type == "employee" and self.actor.role not in {"owner", "administrator"}: q = q.where(DiningTable.branch_id == self.actor.employee.branch_id)
        rows = (await self.db.execute(q.order_by(DiningTable.floor, DiningTable.name))).scalars().all()
        return [row_dict(r, ("id", "branch_id", "name", "floor", "seats", "x", "y", "active")) for r in rows]

    def manager(self):
        return self.actor.role in {"owner", "administrator"} or has_permission(self.actor.permissions or {}, "restaurant_manage")

    async def save_table(self, data, table_id=None):
        await self.require_write('restaurant')
        permit(self.actor, "restaurant_manage")
        await self.feature("restaurant"); await self.branch(data.branch_id)
        table = await self.db.get(DiningTable, table_id) if table_id else DiningTable(company_id=self.actor.company_id)
        if not table or table.company_id != self.actor.company_id: raise HTTPException(404, "Table not found")
        if table_id:
            await self.branch(table.branch_id)
            if table.branch_id != data.branch_id: raise HTTPException(409, "Create another table to change branch")
            if not data.active and (await self.db.execute(select(CommerceOrder.id).where(CommerceOrder.table_id == table.id, CommerceOrder.status == "open"))).first(): raise HTTPException(409, "Close or transfer open bills before disabling this table")
        for key, value in data.model_dump().items(): setattr(table, key, value)
        self.db.add(table); await self.db.flush()
        self.audit("dining_table_saved", table_id=table.id); await self.db.commit()
        return row_dict(table, ("id", "name", "floor", "seats", "x", "y", "branch_id", "active"))

    async def valid_table(self, table_id, branch_id):
        if table_id:
            table = await self.db.get(DiningTable, table_id)
            if not table or table.company_id != self.actor.company_id or table.branch_id != branch_id or not table.active:
                raise HTTPException(400, "Table is not available in this branch")
            return table

    async def valid_waiter(self, waiter_id, branch_id):
        if waiter_id:
            waiter = await self.db.get(Employee, waiter_id)
            if not waiter or waiter.company_id != self.actor.company_id or waiter.branch_id != branch_id or not waiter.active or waiter.deleted:
                raise HTTPException(400, "Employee is not active in this branch")
            return waiter

    async def guest(self, guest_id, branch_id):
        guest = (await self.db.execute(select(GuestAccount).where(GuestAccount.id == guest_id).with_for_update())).scalar_one_or_none()
        if not guest or guest.company_id != self.actor.company_id or guest.branch_id != branch_id or not guest.active:
            raise HTTPException(400, "Guest account is not active in this branch")
        return guest

    async def create_order(self, data):
        permit(self.actor, "quotations_manage" if data.kind == "quotation" else "orders_manage")
        if data.kind == "quotation" and (data.table_id or data.guest_id): raise HTTPException(422, "Quotations do not use restaurant tables or room accounts")
        await self.branch(data.branch_id)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {'key': 'phase11-order:' + str(self.actor.company_id) + ':' + str(data.request_id)})
        # A register lock serializes repeated create requests before uniqueness.
        device = (await self.db.execute(select(Device).where(Device.id == data.device_id, Device.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not device or device.branch_id != data.branch_id or device.removed_at or device.deactivated_at or not device.active or device.deleted:
            raise HTTPException(400, "Register is not active in this branch")
        if self.actor.actor_type == "employee" and (not self.actor.pos_session or self.actor.pos_session.device_id != device.id):
            raise HTTPException(403, "Use the authenticated register")
        from app.sales.commands import fingerprint, actor_identity
        command_hash, command_actor = fingerprint(data), actor_identity(self.actor, self.actor.company_id)
        existing = (await self.db.execute(select(CommerceOrder).where(CommerceOrder.company_id == self.actor.company_id, CommerceOrder.request_id == data.request_id))).scalar_one_or_none()
        if existing:
            if (existing.branch_id, existing.device_id, existing.kind) != (data.branch_id, data.device_id, data.kind): raise HTTPException(409, "Order request identity is already bound to another register or type")
            await self.order(existing.id)
            if not existing.creation_payload_hash: raise HTTPException(409, 'Existing order has no complete creation proof; retrieve its current state')
            if (existing.creation_actor_type, existing.creation_actor_id) != (self.actor.actor_type, command_actor): raise HTTPException(403, 'Original order belongs to another actor')
            if existing.creation_payload_hash != command_hash: raise HTTPException(409, 'Order creation payload differs')
            return await self.order_out(existing)
        module = 'wholesale' if data.kind == 'quotation' else 'hospitality' if data.kind == 'room_service' else 'restaurant'
        await self.require_write(module)
        await self.feature(module)
        waiter_id = data.waiter_id or (self.actor.employee.id if self.actor.employee else None)
        if not self.manager() and self.actor.employee and waiter_id != self.actor.employee.id:
            raise HTTPException(403, "Only a restaurant manager can assign another waiter")
        await self.valid_waiter(waiter_id, data.branch_id); await self.valid_table(data.table_id, data.branch_id)
        if data.guest_id: await self.guest(data.guest_id, data.branch_id)
        if data.customer_id:
            customer = await self.db.get(Customer, data.customer_id)
            if not customer or customer.company_id != self.actor.company_id or not customer.active or customer.deleted: raise HTTPException(400, "Customer not found")
        row = CommerceOrder(company_id=self.actor.company_id, branch_id=data.branch_id, device_id=device.id, waiter_id=waiter_id,
            table_id=data.table_id, guest_id=data.guest_id, customer_id=data.customer_id, kind=data.kind, request_id=data.request_id,
            number=f"O-{uuid.uuid4().hex[:16].upper()}", status="open", version=1, notes=data.notes)
        if row.kind == 'quotation': row.quotation_status = 'draft'
        row.creation_payload_hash = command_hash; row.creation_actor_type = self.actor.actor_type; row.creation_actor_id = command_actor
        self.db.add(row); await self.db.flush()
        self.audit("commerce_order_opened", order_id=row.id, kind=row.kind); await self.commit_operation()
        return await self.order_out(row)

    async def order(self, order_id, *, version=None, edit=False, settle=False):
        row = (await self.db.execute(select(CommerceOrder).where(CommerceOrder.id == order_id, CommerceOrder.company_id == self.actor.company_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not row: raise HTTPException(404, "Order not found")
        await self.branch(row.branch_id)
        permit(self.actor, "orders_settle" if settle else "quotations_manage" if row.kind == "quotation" else "orders_manage")
        if self.actor.employee and not self.manager() and not settle and row.waiter_id != self.actor.employee.id:
            raise HTTPException(403, "Order belongs to another employee")
        if edit: await self.require_write('wholesale' if row.kind == 'quotation' else 'hospitality' if row.kind == 'room_service' else 'restaurant')
        if edit and row.kind == 'quotation' and row.quotation_status != 'draft': raise HTTPException(409, 'Quotation terms are frozen; create a new draft')
        if edit and row.status != "open": raise HTTPException(409, "Order is locked")
        if version is not None and row.version != version: raise HTTPException(409, "Order changed. Reload before retrying")
        return row

    async def order_items(self, row):
        return (await self.db.execute(select(CommerceOrderItem).where(CommerceOrderItem.order_id == row.id).order_by(CommerceOrderItem.id))).scalars().all()

    async def order_out(self, row):
        from .quotations import state
        table = await self.db.get(DiningTable, row.table_id) if row.table_id else None
        waiter = await self.db.get(Employee, row.waiter_id) if row.waiter_id else None
        items = await self.order_items(row)
        return {**row_dict(row, ("id", "number", "kind", "status", "version", "branch_id", "device_id", "table_id", "waiter_id", "guest_id", "customer_id", "parent_id", "sale_id", "notes", "created_at")),
            'quotation_status': state(row) if row.kind=='quotation' else None, 'quotation_valid_until':row.quotation_valid_until, 'quotation_terms':row.quotation_terms,
            "table_name": table.name if table else "Takeaway", "waiter_name": waiter.name if waiter else "Unassigned",
            "items": [row_dict(i, ("id", "product_id", "variant_id", "name", "quantity", "sent_quantity", "price", "unit", "notes")) for i in items],
            "estimated_subtotal": str(sum((i.quantity * i.price for i in items), Decimal("0"))), "estimate_only": row.quotation_terms is None}

    async def refresh_price_estimates(self, row):
        # Reuse Phase 7A's configured customer-price lookup. Estimates do not
        # create tax/payment records or reserve stock, and checkout revalidates.
        from app.sales.repository import SalesRepository
        repo = SalesRepository(self.db)
        items = await self.order_items(row)
        customer = await self.db.get(Customer, row.customer_id) if row.customer_id else None
        quantities = {}
        for item in items:
            key = (item.product_id, item.variant_id)
            quantities[key] = quantities.get(key, Decimal("0")) + item.quantity
        for item in items:
            product = await self.db.get(Product, item.product_id)
            variant = await self.db.get(ProductVariant, item.variant_id) if item.variant_id else None
            level = await repo.get_price_level(row.company_id, product.id, customer.price_level_name, quantities[(item.product_id, item.variant_id)]) if customer and customer.price_level_name else None
            item.price = level.price if level else variant.selling_price if variant and variant.selling_price is not None else product.selling_price

    async def list_orders(self, kind=None):
        allowed = self.actor.role in {"owner", "administrator"} or any(has_permission(self.actor.permissions or {}, p) for p in ("orders_manage", "orders_settle", "restaurant_manage", "quotations_manage", "hospitality_manage"))
        if not allowed: raise HTTPException(403, "Permission denied")
        q = select(CommerceOrder).where(CommerceOrder.company_id == self.actor.company_id)
        if kind: q = q.where(CommerceOrder.kind == kind)
        if self.actor.employee and self.actor.role not in {"owner", "administrator"}:
            q = q.where(CommerceOrder.branch_id == self.actor.employee.branch_id)
            if not self.manager() and not has_permission(self.actor.permissions or {}, "orders_settle"):
                q = q.where(CommerceOrder.waiter_id == self.actor.employee.id)
        rows = (await self.db.execute(q.order_by(CommerceOrder.created_at.desc()).limit(100))).scalars().all()
        return [await self.order_out(row) for row in rows]

    async def add_item(self, order_id, data):
        await self.require_write()
        row = await self.order(order_id, version=data.version, edit=True)
        product = await self.db.get(Product, data.product_id)
        if not product or product.company_id != self.actor.company_id or not product.active or product.deleted: raise HTTPException(400, "Product is not active")
        variant = None
        variants = (await self.db.execute(select(ProductVariant).where(ProductVariant.product_id == product.id, ProductVariant.active == True, ProductVariant.deleted == False))).scalars().all()
        if data.variant_id:
            variant = next((v for v in variants if v.id == data.variant_id and v.company_id == self.actor.company_id), None)
            if not variant: raise HTTPException(400, "Variant not found")
        elif variants: raise HTTPException(400, "Select a product variant")
        price = variant.selling_price if variant and variant.selling_price is not None else product.selling_price
        if price is None or price <= 0: raise HTTPException(400, "Product needs a selling price")
        profile = await self.db.get(BusinessProfile, row.company_id)
        charge = bool(profile and product.id in {profile.tip_product_id, profile.service_product_id})
        self.db.add(CommerceOrderItem(order_id=row.id, product_id=product.id, variant_id=data.variant_id, category_id=product.category_id,
            name=product.name + (f" ({variant.name})" if variant else ""), quantity=data.quantity, sent_quantity=data.quantity if charge else 0,
            price=price, unit=product.unit, notes=data.notes))
        row.version += 1
        await self.db.flush(); await self.refresh_price_estimates(row)
        self.audit("order_item_added", order_id=row.id, product_id=product.id, quantity=str(data.quantity)); await self.commit_operation()
        return await self.order_out(row)

    async def edit_item(self, order_id, item_id, data):
        await self.require_write()
        row = await self.order(order_id, version=data.version, edit=True)
        item = next((i for i in await self.order_items(row) if i.id == item_id), None)
        if not item: raise HTTPException(404, "Order item not found")
        if item.sent_quantity > data.quantity and not self.manager():
            permit(self.actor, "sales_cancel")
        # Sent preparation notes cannot be silently changed; create an explicit
        # amendment line instead so kitchen output remains accountable.
        if item.sent_quantity and item.notes != data.notes: raise HTTPException(409, "Add an amendment item for new preparation notes")
        item.quantity, item.notes = data.quantity, data.notes
        profile = await self.db.get(BusinessProfile, row.company_id)
        if profile and item.product_id in {profile.tip_product_id, profile.service_product_id}: item.sent_quantity = item.quantity
        row.version += 1
        await self.db.flush(); await self.refresh_price_estimates(row)
        self.audit("order_item_changed", order_id=row.id, item_id=item.id, quantity=str(data.quantity)); await self.commit_operation()
        return await self.order_out(row)

    async def send_kitchen(self, order_id, version):
        from app.subscriptions.commercial import enforce_feature
        row = await self.order(order_id, version=version)
        if row.status != "open": raise HTTPException(409, "Order is locked")
        permit(self.actor, "orders_send")
        if row.kind == "quotation": raise HTTPException(400, "Quotations cannot be sent to kitchens")
        items = await self.order_items(row)
        table = await self.valid_table(row.table_id, row.branch_id)
        waiter = await self.valid_waiter(row.waiter_id, row.branch_id)
        context = {"table": table.name if table else "Takeaway", "waiter": waiter.name if waiter else "Unassigned"}
        changed_context = bool(row.last_dispatch_context and row.last_dispatch_context != context)
        profile = await self.db.get(BusinessProfile, row.company_id)
        charges = {profile.tip_product_id, profile.service_product_id} if profile else set()
        changed = [i for i in items if i.quantity != i.sent_quantity]
        if not changed and not changed_context: return {"jobs": [], "order": await self.order_out(row)}
        await self.require_write('hospitality' if row.kind == 'room_service' else 'restaurant', 'kitchen_printing')
        await enforce_feature(self.db,self.actor.company_id,'kitchen_printing')
        stations = (await self.db.execute(select(PrinterStation).where(PrinterStation.company_id == row.company_id,
            PrinterStation.branch_id == row.branch_id, PrinterStation.device_id == row.device_id, PrinterStation.active == True,
            PrinterStation.purpose.in_(["kitchen", "bar"])).order_by(PrinterStation.id).with_for_update())).scalars().all()
        routed = set(); jobs = []
        for station in stations:
            routes = (await self.db.execute(select(PrinterRoute).where(PrinterRoute.station_id == station.id))).scalars().all()
            match = lambda item: any((r.target_type == "product" and r.target_id == item.product_id) or (r.target_type == "category" and r.target_id == item.category_id) for r in routes)
            selected = [i for i in changed if match(i)]
            if changed_context: selected = [i for i in items if (i.quantity > 0 or i in changed) and i.product_id not in charges and match(i)]
            if not selected: continue
            routed.update(i.id for i in selected)
            cancellation_only = all(i.quantity <= i.sent_quantity for i in selected)
            if any(i.quantity < i.sent_quantity for i in selected):
                # Do not leave an obsolete preparation task actionable after
                # a cancellation. Preserve its immutable ticket, but require
                # staff review of the amendment instead of cooking old counts.
                previous = (await self.db.execute(select(KitchenTicket).where(KitchenTicket.order_id == row.id,
                    KitchenTicket.station_id == station.id, KitchenTicket.status.notin_(["served", "acknowledged"])).with_for_update())).scalars().all()
                for ticket in previous: ticket.status = "needs_review"
            payload = {"title": "TABLE / WAITER UPDATE — DO NOT PREPARE AGAIN" if changed_context and not changed else "CANCEL PREPARATION — ORDER UPDATE" if cancellation_only else "KITCHEN ORDER UPDATE",
                "order_number": row.number, **context, "created_at": datetime.now(timezone.utc).isoformat(),
                "notes": row.notes, "previous_location": row.last_dispatch_context, "order_version": row.version,
                "items": [{"name": i.name, "quantity": str(i.quantity - i.sent_quantity) if i in changed else "0",
                    "selling_unit": i.unit, "notes": ("CANCEL " if i.quantity < i.sent_quantity else "") + i.notes} for i in selected],
                "printer": {"transport": station.transport, "address": station.address, "paper_width": station.paper_width, "name": station.name}}
            job = PrintJob(company_id=row.company_id, station_id=station.id, order_id=row.id,
                requested_employee_id=self.actor.employee.id if self.actor.employee else None,
                request_key=f"order:{row.id}:{row.version}", kind="kot", payload=payload, payload_hash=digest(payload), status="pending", attempts=0)
            self.db.add(job); await self.db.flush()
            ticket = KitchenTicket(company_id=row.company_id, order_id=row.id, station_id=station.id, print_job_id=job.id, version=row.version, status="queued")
            self.db.add(ticket)
            jobs.append(self.job_out(job))
        required = [i for i in items if i.product_id not in charges and (i.quantity > 0 or i in changed)] if changed_context else changed
        if any(i.id not in routed for i in required):
            raise HTTPException(409, "Some changed items have no kitchen/bar routing. Nothing was dispatched")
        for item in changed: item.sent_quantity = item.quantity
        row.last_dispatch_context = context; row.version += 1
        self.audit("order_kitchen_dispatched", order_id=row.id, version=version, jobs=[str(j["id"]) for j in jobs]); await self.commit_operation()
        return {"jobs": jobs, "order": await self.order_out(row)}

    async def move(self, order_id, data):
        await self.require_write()
        row = await self.order(order_id, version=data.version, edit=True)
        permit(self.actor, "restaurant_manage")
        items = await self.order_items(row)
        if row.last_dispatch_context and any(i.quantity != i.sent_quantity for i in items):
            raise HTTPException(409, "Dispatch pending item changes before transferring this order")
        await self.valid_table(data.table_id, row.branch_id); await self.valid_waiter(data.waiter_id, row.branch_id)
        row.table_id = data.table_id
        if data.waiter_id: row.waiter_id = data.waiter_id
        row.version += 1
        self.audit("order_transferred", order_id=row.id, table_id=row.table_id, waiter_id=row.waiter_id)
        if row.last_dispatch_context:
            dispatched = await self.send_kitchen(row.id, row.version)
            # A no-op kitchen dispatch intentionally does not commit. Persist
            # the authorized assignment/version change even in that case.
            await self.db.commit()
            return {**dispatched["order"], "print_jobs": dispatched["jobs"]}
        await self.db.commit()
        return {**await self.order_out(row), "print_jobs": []}

    async def split(self, order_id, data):
        await self.require_write()
        row = await self.order(order_id, version=data.version, edit=True)
        permit(self.actor, "restaurant_manage")
        if row.kind == 'quotation': raise HTTPException(409,'Create a new quotation draft instead of splitting its authority')
        items = [i for i in await self.order_items(row) if i.quantity > 0]
        if data.item_ids and data.quantities:
            raise HTTPException(400, "Choose whole lines or quantities, not both")
        quantities = {entry.item_id: entry.quantity for entry in data.quantities}
        if len(quantities) != len(data.quantities) or len(set(data.item_ids)) != len(data.item_ids):
            raise HTTPException(400, "Duplicate split lines")
        if data.item_ids: quantities = {i.id: i.quantity for i in items if i.id in data.item_ids}
        selected = [i for i in items if i.id in quantities]
        if not selected or len(selected) != len(quantities) or (data.item_ids and len(selected) != len(data.item_ids)):
            raise HTTPException(400, "Select active lines")
        if any(quantities[i.id] > i.quantity for i in selected):
            raise HTTPException(400, "Split quantity exceeds the bill quantity")
        if sum(quantities.values()) >= sum(i.quantity for i in items):
            raise HTTPException(400, "Leave at least one item on the original bill")
        # Splitting unacknowledged kitchen changes makes preparation lineage
        # ambiguous. Dispatch amendments first; never send split food twice.
        if row.last_dispatch_context and any(i.quantity != i.sent_quantity for i in items):
            raise HTTPException(409, "Dispatch pending changes before splitting")
        child = CommerceOrder(company_id=row.company_id, branch_id=row.branch_id, device_id=row.device_id, waiter_id=row.waiter_id,
            table_id=row.table_id, customer_id=row.customer_id, guest_id=row.guest_id, parent_id=row.id, kind=row.kind,
            request_id=data.request_id, number=f"O-{uuid.uuid4().hex[:16].upper()}", status="open", version=1, notes=row.notes,
            last_dispatch_context=row.last_dispatch_context)
        self.db.add(child); await self.db.flush()
        for item in selected:
            amount = quantities[item.id]
            if amount == item.quantity:
                item.order_id = child.id
            else:
                sent = min(item.sent_quantity, amount)
                self.db.add(CommerceOrderItem(order_id=child.id, product_id=item.product_id,
                    variant_id=item.variant_id, category_id=item.category_id, name=item.name,
                    quantity=amount, sent_quantity=sent, price=item.price, unit=item.unit, notes=item.notes))
                item.quantity -= amount
                item.sent_quantity -= sent
        row.version += 1
        await self.db.flush(); await self.refresh_price_estimates(row); await self.refresh_price_estimates(child)
        self.audit("order_bill_split", source_id=row.id, target_id=child.id,
            quantities={str(key): str(value) for key, value in quantities.items()}); await self.db.commit()
        return {"source": await self.order_out(row), "target": await self.order_out(child)}

    async def merge(self, order_id, data):
        await self.require_write()
        if order_id == data.source_id: raise HTTPException(400, "Choose different orders")
        permit(self.actor, "restaurant_manage")
        # Stable lock order avoids opposite-direction merge deadlocks.
        locked = {key: await self.order(key, edit=True) for key in sorted([order_id, data.source_id], key=str)}
        target, source = locked[order_id], locked[data.source_id]
        if target.kind == 'quotation' or source.kind == 'quotation': raise HTTPException(409,'Create a new quotation draft instead of merging its authority')
        if (target.branch_id, target.device_id, target.customer_id, target.guest_id, target.kind) != (source.branch_id, source.device_id, source.customer_id, source.guest_id, source.kind): raise HTTPException(409, "Bills must share branch, register, guest/customer and type")
        if target.version != data.version or source.version != data.source_version: raise HTTPException(409, "Order changed. Reload")
        if any(i.sent_quantity > 0 for i in await self.order_items(source)) and (target.table_id != source.table_id or target.waiter_id != source.waiter_id):
            raise HTTPException(409, "Transfer sent orders to the same table/waiter before merging")
        for item in await self.order_items(source): item.order_id = target.id
        source.status = "merged"; source.parent_id = target.id; source.version += 1; target.version += 1
        await self.db.flush(); await self.refresh_price_estimates(target)
        self.audit("order_bills_merged", source_id=source.id, target_id=target.id); await self.db.commit()
        return await self.order_out(target)

    async def cancel(self, order_id, version):
        await self.require_write()
        row = await self.order(order_id, version=version, edit=True)
        permit(self.actor, "restaurant_manage")
        items = await self.order_items(row)
        profile = await self.db.get(BusinessProfile, row.company_id)
        charges = {profile.tip_product_id, profile.service_product_id} if profile else set()
        if any(i.sent_quantity for i in items if i.product_id not in charges): raise HTTPException(409, "Remove sent items and dispatch cancellation tickets before cancelling")
        row.status = "cancelled"; row.version += 1
        self.audit("order_cancelled", order_id=row.id); await self.db.commit()
        return await self.order_out(row)

    async def settle(self, order_id, data):
        row = await self.order(order_id, settle=True)
        from app.sales.commands import fingerprint, actor_identity
        command_hash, command_actor = fingerprint(data), actor_identity(self.actor, self.actor.company_id)
        if self.actor.employee and (not self.actor.pos_session or self.actor.pos_session.device_id != row.device_id): raise HTTPException(403, 'Settle on the assigned register')
        if data.payment.company_id != row.company_id: raise HTTPException(403, 'Forbidden')
        if row.status == "settled":
            if not row.settlement_payload_hash: raise HTTPException(409, 'Existing settlement has no complete replay proof; retrieve the original sale')
            if (row.settlement_actor_type, row.settlement_actor_id) != (self.actor.actor_type, command_actor): raise HTTPException(403, 'Original settlement belongs to another actor')
            if row.settlement_payload_hash != command_hash: raise HTTPException(409, 'Settlement payload differs')
            return {"sale_id": row.sale_id, "order": await self.order_out(row), "already_settled": True}
        await self.require_write('wholesale' if row.kind == 'quotation' else 'hospitality' if row.kind == 'room_service' else 'restaurant')
        if row.status != "open" or row.version != data.version: raise HTTPException(409, "Order changed or locked")
        permit(self.actor, "sales_process")
        if self.actor.employee and (not self.actor.pos_session or self.actor.pos_session.device_id != row.device_id): raise HTTPException(403, "Settle on the assigned register")
        if data.payment.company_id != row.company_id: raise HTTPException(403, "Forbidden")
        if data.payment.client_created_at or data.payment.offline_shift_token: raise HTTPException(409, "Open-order settlement is online-only; preserve pending offline sales for their existing sync workflow")
        if row.kind == 'quotation':
            if data.charge_to_room: raise HTTPException(409,'Quotation customer terms are frozen; room charging is unavailable')
            from .quotations import require_conversion
            await require_conversion(self,row,data.payment)
        items = [i for i in await self.order_items(row) if i.quantity > 0]
        if not items: raise HTTPException(400, "Order is empty")
        if row.kind != "quotation" and any(i.quantity != i.sent_quantity for i in await self.order_items(row)):
            raise HTTPException(409, "Dispatch item changes to the kitchen before settlement")
        customer_id = row.customer_id
        if data.charge_to_room:
            permit(self.actor, "hospitality_manage")
            if not row.guest_id: raise HTTPException(409, "Assign an active guest account first")
            guest = await self.guest(row.guest_id, row.branch_id)
            customer_id = guest.customer_id
            if data.payment.payment_method != "credit": raise HTTPException(400, "Room charges use the existing customer-credit workflow")
        from app.sales.schema import SaleItemCreate
        from app.sales.repository import SalesRepository
        from app.sales.service import SalesService
        grouped = {}
        for item in items:
            identity = (item.product_id, item.variant_id, item.unit)
            grouped[identity] = grouped.get(identity, Decimal("0")) + item.quantity
        payment = data.payment.model_copy(update={"company_id": row.company_id, "branch_id": row.branch_id, "device_id": row.device_id,
            "client_sale_id": row.id, "customer_id": customer_id,
            "items": [SaleItemCreate(product_id=p, variant_id=v, quantity=q, selling_unit=u) for (p, v, u), q in grouped.items()]})
        if row.kind == 'quotation': payment = payment.model_copy(update={'discount_amount': Decimal('0'), 'sale_discount_amount': Decimal('0')})
        try:
            sale = await SalesService(SalesRepository(self.db, commit_on_save=False)).create_sale(payment, actor=self.actor)
            if row.kind == 'quotation':
                from .quotations import validate_sale
                await validate_sale(self,row,sale)
            row.sale_id = sale.id; row.status = "settled"; row.version += 1
            row.settlement_payload_hash = command_hash; row.settlement_actor_type = self.actor.actor_type; row.settlement_actor_id = command_actor
            self.audit("order_settled", order_id=row.id, sale_id=sale.id, guest_id=row.guest_id, room_charge=data.charge_to_room)
            await self.db.commit()
        except Exception:
            await self.db.rollback(); raise
        return {"sale_id": sale.id, "receipt_number": sale.receipt_number, "order": await self.order_out(row), "already_settled": False}

    async def kitchen(self):
        allowed = [purpose for purpose, permission in (("kitchen", "kitchen_view"), ("bar", "bar_view")) if self.actor.role in {"owner", "administrator"} or has_permission(self.actor.permissions or {}, permission)]
        if not allowed: raise HTTPException(403, "Permission denied")
        q = select(KitchenTicket, PrintJob, CommerceOrder, PrinterStation).join(PrintJob, PrintJob.id == KitchenTicket.print_job_id).join(CommerceOrder, CommerceOrder.id == KitchenTicket.order_id).join(PrinterStation, PrinterStation.id == KitchenTicket.station_id).where(KitchenTicket.company_id == self.actor.company_id, PrinterStation.purpose.in_(allowed))
        if self.actor.employee and self.actor.role not in {"owner", "administrator"}: q = q.where(CommerceOrder.branch_id == self.actor.employee.branch_id)
        rows = (await self.db.execute(q.order_by(KitchenTicket.created_at.desc()).limit(100))).all()
        output = []
        for ticket, job, order, station in rows:
            table = await self.db.get(DiningTable, order.table_id) if order.table_id else None
            waiter = await self.db.get(Employee, order.waiter_id) if order.waiter_id else None
            output.append({"id": ticket.id, "order_id": order.id, "status": ticket.status, "station_name": station.name,
                "purpose": station.purpose, "payload": job.payload, "current_table": table.name if table else "Takeaway",
                "current_waiter": waiter.name if waiter else "Unassigned", "print_status": job.status, "created_at": ticket.created_at})
        return output

    async def kitchen_state(self, ticket_id, status):
        ticket = (await self.db.execute(select(KitchenTicket).where(KitchenTicket.id == ticket_id, KitchenTicket.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not ticket: raise HTTPException(404, "Kitchen ticket not found")
        order = await self.db.get(CommerceOrder, ticket.order_id); await self.branch(order.branch_id)
        station = await self.db.get(PrinterStation, ticket.station_id)
        permit(self.actor, "bar_update" if station.purpose == "bar" else "kitchen_update")
        if status == ticket.status: return {"status": status}
        await self.require_write('restaurant')
        job = await self.db.get(PrintJob, ticket.print_job_id)
        informational = all(Decimal(item["quantity"]) <= 0 for item in job.payload["items"])
        next_state = "acknowledged" if ticket.status == "needs_review" or (informational and ticket.status == "queued") else {"queued": "preparing", "preparing": "ready", "ready": "served"}.get(ticket.status)
        if next_state != status: raise HTTPException(409, "Invalid kitchen status transition")
        ticket.status = status
        self.audit("kitchen_status_changed", ticket_id=ticket.id, status=status); await self.commit_operation()
        return {"status": status}

    async def rooms(self):
        permit(self.actor, "hospitality_manage")
        q = select(HospitalityRoom).where(HospitalityRoom.company_id == self.actor.company_id)
        if self.actor.employee and self.actor.role not in {"owner", "administrator"}: q = q.where(HospitalityRoom.branch_id == self.actor.employee.branch_id)
        rooms = (await self.db.execute(q.order_by(HospitalityRoom.name))).scalars().all()
        output = []
        for room in rooms:
            guests = (await self.db.execute(select(GuestAccount).where(GuestAccount.room_id == room.id, GuestAccount.active == True))).scalars().all()
            output.append({**row_dict(room, ("id", "branch_id", "name", "active")), "guests": [row_dict(g, ("id", "customer_id", "active")) for g in guests]})
        return output

    async def save_room(self, data, room_id=None):
        await self.require_write('hospitality')
        permit(self.actor, "hospitality_manage"); await self.feature("hospitality"); await self.branch(data.branch_id)
        room = await self.db.get(HospitalityRoom, room_id) if room_id else HospitalityRoom(company_id=self.actor.company_id)
        if not room or room.company_id != self.actor.company_id: raise HTTPException(404, "Room not found")
        if room_id:
            await self.branch(room.branch_id)
            if room.branch_id != data.branch_id: raise HTTPException(409, "Create a room to change branch")
            if not data.active and (await self.db.execute(select(GuestAccount.id).where(GuestAccount.room_id == room.id, GuestAccount.active == True))).first(): raise HTTPException(409, "Close the active guest account first")
        if (await self.db.execute(select(HospitalityRoom.id).where(HospitalityRoom.company_id == self.actor.company_id, HospitalityRoom.branch_id == data.branch_id, HospitalityRoom.name == data.name, HospitalityRoom.id != room_id if room_id else True))).first(): raise HTTPException(409, "Room name already exists")
        for key, value in data.model_dump().items(): setattr(room, key, value)
        self.db.add(room); await self.db.flush()
        self.audit("hospitality_room_saved", room_id=room.id); await self.db.commit()
        return {"id": room.id}

    async def open_guest(self, data):
        await self.require_write('hospitality')
        permit(self.actor, "hospitality_manage"); await self.feature("hospitality")
        room = (await self.db.execute(select(HospitalityRoom).where(HospitalityRoom.id == data.room_id, HospitalityRoom.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not room or not room.active: raise HTTPException(404, "Room not available")
        await self.branch(room.branch_id)
        customer = await self.db.get(Customer, data.customer_id)
        if not customer or customer.company_id != self.actor.company_id or not customer.active or customer.deleted: raise HTTPException(400, "Customer not active")
        if (await self.db.execute(select(GuestAccount.id).where(GuestAccount.room_id == room.id, GuestAccount.active == True))).first(): raise HTTPException(409, "Room already has an active guest account")
        guest = GuestAccount(company_id=self.actor.company_id, branch_id=room.branch_id, room_id=room.id, customer_id=customer.id, active=True)
        self.db.add(guest); await self.db.flush(); self.audit("guest_account_opened", guest_id=guest.id); await self.db.commit()
        return {"id": guest.id}

    async def folio(self, guest_id):
        permit(self.actor, "hospitality_manage")
        guest = await self.db.get(GuestAccount, guest_id)
        if not guest or guest.company_id != self.actor.company_id: raise HTTPException(404, "Guest not found")
        await self.branch(guest.branch_id)
        customer = await self.db.get(Customer, guest.customer_id)
        rows = (await self.db.execute(select(Sale, CreditReceivable).join(CommerceOrder, or_(CommerceOrder.sale_id == Sale.id, CommerceOrder.sale_id == Sale.original_sale_id)).outerjoin(CreditReceivable, CreditReceivable.sale_id == Sale.id).where(CommerceOrder.guest_id == guest.id, CommerceOrder.company_id == self.actor.company_id))).all()
        return {"guest_id": guest.id, "guest_name": customer.name, "customer_id": customer.id, "charges": [{"sale_id": sale.id, "receipt_number": sale.receipt_number, "amount": str(sale.total_amount), "currency": sale.base_currency_code, "outstanding": str(receivable.outstanding_balance) if receivable else "0"} for sale, receivable in rows]}

    async def close_guest(self, guest_id):
        await self.require_write('hospitality')
        permit(self.actor, "hospitality_manage")
        guest = (await self.db.execute(select(GuestAccount).where(GuestAccount.id == guest_id, GuestAccount.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not guest: raise HTTPException(404, "Guest not found")
        await self.branch(guest.branch_id)
        # Lock the customer so a concurrent new credit posting cannot race the
        # outstanding-balance check. Existing credit service uses this lock too.
        await self.db.execute(select(Customer.id).where(Customer.id == guest.customer_id).with_for_update())
        if (await self.db.execute(select(CommerceOrder.id).where(CommerceOrder.guest_id == guest.id, CommerceOrder.status == "open"))).first(): raise HTTPException(409, "Close the guest's open orders first")
        if (await self.db.execute(select(CreditReceivable.id).where(CreditReceivable.company_id == self.actor.company_id, CreditReceivable.customer_id == guest.customer_id, CreditReceivable.outstanding_balance > 0))).first(): raise HTTPException(409, "Settle the guest's outstanding customer credit first")
        if guest.active:
            guest.active = False; self.audit("guest_account_closed", guest_id=guest.id); await self.db.commit()
        return {"closed": True}

    async def batches(self):
        permit(self.actor, "batches_view")
        from .batches import business_today
        today = await business_today(self.db, self.actor.company_id)
        q = select(ProductBatch, Product.name, ProductVariant.name).join(Product, Product.id == ProductBatch.product_id).outerjoin(ProductVariant, ProductVariant.id == ProductBatch.variant_id).where(ProductBatch.company_id == self.actor.company_id)
        if self.actor.employee and self.actor.role not in {"owner", "administrator"}: q = q.where(ProductBatch.branch_id == self.actor.employee.branch_id)
        rows = (await self.db.execute(q.order_by(ProductBatch.expires_on).limit(1000))).all()
        return [{**row_dict(batch, ("id", "branch_id", "product_id", "variant_id", "code", "expires_on", "quantity")), "product_name": name, "variant_name": variant_name,
            "expired": batch.expires_on < today, "expires_soon": 0 <= (batch.expires_on - today).days <= 30} for batch, name, variant_name in rows]

    async def assign_batch(self, data):
        await self.require_write('pharmacy')
        permit(self.actor, "batches_manage"); await self.feature("pharmacy"); await self.branch(data.branch_id)
        from app.inventory.stock_repository import BranchStockRepository
        stock = BranchStockRepository(self.db)
        product = await stock.get_product_for_update(self.actor.company_id, data.product_id)
        if not product.track_inventory or product.product_type not in {"standard", "variable_weight"}: raise HTTPException(409, "Batch tracking requires a standard stock product")
        from .batch_stock import resolve_batch_variant
        variant = await resolve_batch_variant(self.db, self.actor.company_id, product.id, data.variant_id)
        branch = await self.branch(data.branch_id)
        if variant:
            from app.sales.repository import SalesRepository
            balance = await SalesRepository(self.db).get_variant_balance(self.actor.company_id, branch, product.id, variant.id)
        else: balance = await stock.get_balance_for_update(self.actor.company_id, branch, product)
        allocated = (await self.db.execute(select(func.coalesce(func.sum(ProductBatch.quantity), 0)).where(ProductBatch.company_id == self.actor.company_id, ProductBatch.branch_id == branch.id, ProductBatch.product_id == product.id, ProductBatch.variant_id == data.variant_id))).scalar_one()
        from .batches import pending_return_quantity
        held = await pending_return_quantity(self.db, self.actor.company_id, branch.id, product.id, data.variant_id)
        if Decimal(allocated) + data.quantity > Decimal(balance.quantity) - held: raise HTTPException(409, "Batch assignments cannot exceed inspected physical stock; receive stock or inspect pending customer returns first")
        if (await self.db.execute(select(ProductBatch.id).where(ProductBatch.company_id == self.actor.company_id, ProductBatch.branch_id == branch.id, ProductBatch.product_id == product.id, ProductBatch.variant_id == data.variant_id, ProductBatch.code == data.code))).first():
            raise HTTPException(409, "Batch code already assigned; review the existing lot rather than replaying an assignment")
        batch = ProductBatch(company_id=self.actor.company_id, **data.model_dump()); self.db.add(batch); await self.db.flush()
        self.audit("batch_stock_assigned", batch_id=batch.id, quantity=str(data.quantity), physical_stock_unchanged=True); await self.db.commit()
        return {"id": batch.id}

    async def reports(self, start, end):
        permit(self.actor, "revenue_view")
        if start > end: raise HTTPException(400, "Invalid date range")
        from app.models import CompanySetting
        settings = (await self.db.execute(select(CompanySetting).where(CompanySetting.company_id == self.actor.company_id))).scalar_one_or_none()
        day = func.date(func.timezone(settings.reporting_timezone if settings else "UTC", Sale.created_at))
        q = select(Sale, CommerceOrder).join(CommerceOrder, or_(CommerceOrder.sale_id == Sale.id, CommerceOrder.sale_id == Sale.original_sale_id)).where(CommerceOrder.company_id == self.actor.company_id, day >= start, day <= end)
        if self.actor.employee and self.actor.role not in {"owner", "administrator"}: q = q.where(CommerceOrder.branch_id == self.actor.employee.branch_id)
        rows = (await self.db.execute(q)).all()
        # Keep currencies separate; never aggregate unlike monetary units.
        groups = {}
        for sale, order in rows:
            key = sale.base_currency_code or "legacy-unidentified"
            group = groups.setdefault(key, {"currency": key, "sales": Decimal("0"), "discounts": Decimal("0"), "refunds": Decimal("0"), "orders": 0})
            group["sales"] += sale.total_amount; group["discounts"] += sale.discount_amount or 0
            if sale.original_sale_id: group["refunds"] += abs(sale.total_amount)
            else: group["orders"] += 1
        return {"start": start, "end": end, "currency_totals": [{**g, "sales": str(g["sales"]), "refunds": str(g["refunds"]), "discounts": str(g["discounts"])} for g in groups.values()],
            "records": [{"sale_id": s.id, "order_number": o.number, "receipt_number": s.receipt_number, "waiter_id": o.waiter_id, "amount": str(s.total_amount), "currency": s.base_currency_code} for s, o in rows]}
