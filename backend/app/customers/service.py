from decimal import Decimal

from fastapi import HTTPException
from app.printing.service import permit

from app.customers.repository import CustomerRepository
from app.customers.schema import CreditPolicy, CustomerCreate, CustomerUpdate
from app.financial_access import enforce_actor_company
from app.subscriptions.write_policy import require_new_write
from app.models import AuditEvent, Customer


class CustomerService:
    def __init__(self, repo: CustomerRepository):
        self.repo = repo

    @staticmethod
    def clean(value):
        return value.strip() or None if isinstance(value, str) else value

    @staticmethod
    def can_manage_credit(actor):
        return (
            actor.role in {"owner", "administrator"}
            or bool((actor.permissions or {}).get("customers_manage"))
        )

    @classmethod
    def enforce_cashier_create_policy(cls, data, actor):
        if cls.can_manage_credit(actor):
            return
        if (
            not data.active
            or data.credit_enabled
            or data.unlimited_credit
            or data.credit_limit is not None
            or data.credit_terms_days != 0
        ):
            raise HTTPException(403, "Manager permission is required to configure customer credit or status")

    @classmethod
    def enforce_cashier_update_policy(cls, values, actor):
        if cls.can_manage_credit(actor):
            return
        protected = {
            "customer_code", "active", "credit_enabled", "unlimited_credit",
            "credit_limit", "credit_terms_days", "price_level_name",
        }
        if protected.intersection(values):
            raise HTTPException(403, "Manager permission is required to change customer status or credit configuration")

    @staticmethod
    def view(customer, balance):
        balance = Decimal(balance or 0).quantize(Decimal("0.01"))
        available = None
        if customer.credit_enabled and not customer.unlimited_credit and customer.credit_limit is not None:
            available = max(Decimal("0.00"), Decimal(customer.credit_limit) - balance)
        return {column.name: getattr(customer, column.name) for column in customer.__table__.columns if column.name not in {"deleted", "created_at", "updated_at"}} | {"outstanding_balance": balance, "available_credit": available}

    async def create_checkout(self, data, actor):
        from sqlalchemy import text
        from app.sales.commands import actor_identity, fingerprint
        from app.models import CheckoutCustomerCommand
        identity=actor_identity(actor,data.company_id)
        permit(actor,'customers_view')
        if not data.name.strip():raise HTTPException(422,'Customer name is required')
        command_hash=fingerprint(data)
        await self.repo.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-checkout-customer:'+str(data.request_id)})
        receipt=await self.repo.db.get(CheckoutCustomerCommand,data.request_id)
        if receipt:
            if receipt.company_id != data.company_id:raise HTTPException(409,'Customer request identity is already in use')
            if receipt.actor_type != actor.actor_type or receipt.actor_id != identity:raise HTTPException(403,'Original customer request belongs to another actor')
            if receipt.payload_hash != command_hash:raise HTTPException(409,'Customer request identity has different values')
            customer=await self.repo.get(data.company_id,receipt.customer_id)
            if not customer:raise HTTPException(409,'Original customer requires review')
            return self.view(customer,await self.repo.balance(data.company_id,customer.id))
        await require_new_write(self.repo.db,data.company_id)
        code='POS-'+data.request_id.hex.upper()
        if await self.repo.code_exists(data.company_id,code):raise HTTPException(409,'Generated customer code requires review')
        customer=Customer(company_id=data.company_id,customer_code=code,name=data.name.strip(),phone=self.clean(data.phone),
            email=self.clean(data.email),address=self.clean(data.address),active=True,deleted=False,credit_enabled=False,
            unlimited_credit=False,credit_limit=None,credit_terms_days=0,price_level_name=None)
        self.repo.db.add(customer)
        await self.repo.db.flush([customer])
        self.repo.db.add(CheckoutCustomerCommand(request_id=data.request_id,company_id=data.company_id,customer_id=customer.id,
            actor_type=actor.actor_type,actor_id=identity,payload_hash=command_hash))
        self.repo.db.add(AuditEvent(company_id=data.company_id,actor_user_id=identity if actor.actor_type=='user' else None,
            actor_employee_id=identity if actor.actor_type=='employee' else None,action='checkout_customer_created',details={'request_id':str(data.request_id),'customer_id':str(customer.id)}))
        await self.repo.save(customer)
        return self.view(customer,0)

    async def create(self, data: CustomerCreate, actor):
        permit(actor, "customers_view")
        enforce_actor_company(actor, data.company_id)
        await require_new_write(self.repo.db, data.company_id)
        self.enforce_cashier_create_policy(data, actor)
        code = data.customer_code.strip().upper()
        if await self.repo.code_exists(data.company_id, code):
            raise HTTPException(409, "Customer code already exists")
        customer = Customer(
            company_id=data.company_id, customer_code=code, name=data.name.strip(),
            phone=self.clean(data.phone), email=self.clean(data.email), address=self.clean(data.address),
            credit_enabled=data.credit_enabled, unlimited_credit=data.unlimited_credit,
            credit_limit=data.credit_limit, credit_terms_days=data.credit_terms_days,
            price_level_name=self.clean(data.price_level_name),
            active=data.active, deleted=False,
        )
        self.repo.db.add(AuditEvent(company_id=data.company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="customer_created", details={"customer_code": code}))
        await self.repo.save(customer)
        return self.view(customer, 0)

    async def get(self, company_id, customer_id):
        customer = await self.repo.get(company_id, customer_id)
        if not customer:
            raise HTTPException(404, "Customer not found")
        return self.view(customer, await self.repo.balance(company_id, customer_id))

    async def list(self, company_id, **filters):
        result = await self.repo.list(company_id, **filters)
        if filters.get("with_total"):
            rows, total = result
            return [self.view(customer, balance) for customer, balance in rows], total
        return [self.view(customer, balance) for customer, balance in result]

    async def update(self, company_id, customer_id, data: CustomerUpdate, actor):
        permit(actor, "customers_view")
        enforce_actor_company(actor, company_id)
        await require_new_write(self.repo.db, company_id)
        customer = await self.repo.get(company_id, customer_id, for_update=True)
        if not customer:
            raise HTTPException(404, "Customer not found")
        values = data.model_dump(exclude_unset=True)
        self.enforce_cashier_update_policy(values, actor)
        if "customer_code" in values:
            values["customer_code"] = values["customer_code"].strip().upper()
            if await self.repo.code_exists(company_id, values["customer_code"], customer.id):
                raise HTTPException(409, "Customer code already exists")
        policy = CreditPolicy(
            credit_enabled=values.get("credit_enabled", customer.credit_enabled),
            unlimited_credit=values.get("unlimited_credit", customer.unlimited_credit),
            credit_limit=values.get("credit_limit", customer.credit_limit),
            credit_terms_days=values.get("credit_terms_days", customer.credit_terms_days),
        )
        values.update(policy.model_dump())
        for key, value in values.items():
            if key in {"name", "phone", "email", "address", "price_level_name"}:
                value = self.clean(value)
            setattr(customer, key, value)
        self.repo.db.add(AuditEvent(company_id=company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="customer_updated", details={"customer_id": str(customer.id)}))
        await self.repo.save(customer)
        return self.view(customer, await self.repo.balance(company_id, customer.id))

    async def history(self, company_id, customer_id, **filters):
        if not await self.repo.get(company_id, customer_id):
            raise HTTPException(404, "Customer not found")
        return await self.repo.history(company_id, customer_id, **filters)
