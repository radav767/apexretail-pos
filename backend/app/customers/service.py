from decimal import Decimal

from fastapi import HTTPException

from app.customers.repository import CustomerRepository
from app.customers.schema import CreditPolicy, CustomerCreate, CustomerUpdate
from app.models import AuditEvent, Customer


class CustomerService:
    def __init__(self, repo: CustomerRepository):
        self.repo = repo

    @staticmethod
    def clean(value):
        return value.strip() or None if isinstance(value, str) else value

    @staticmethod
    def view(customer, balance):
        balance = Decimal(balance or 0).quantize(Decimal("0.01"))
        available = None
        if customer.credit_enabled and not customer.unlimited_credit and customer.credit_limit is not None:
            available = max(Decimal("0.00"), Decimal(customer.credit_limit) - balance)
        return {column.name: getattr(customer, column.name) for column in customer.__table__.columns if column.name not in {"deleted", "created_at", "updated_at"}} | {"outstanding_balance": balance, "available_credit": available}

    async def create(self, data: CustomerCreate, actor):
        code = data.customer_code.strip().upper()
        if await self.repo.code_exists(data.company_id, code):
            raise HTTPException(409, "Customer code already exists")
        customer = Customer(
            company_id=data.company_id, customer_code=code, name=data.name.strip(),
            phone=self.clean(data.phone), email=self.clean(data.email), address=self.clean(data.address),
            credit_enabled=data.credit_enabled, unlimited_credit=data.unlimited_credit,
            credit_limit=data.credit_limit, credit_terms_days=data.credit_terms_days,
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
        rows = await self.repo.list(company_id, **filters)
        return [self.view(customer, balance) for customer, balance in rows]

    async def update(self, company_id, customer_id, data: CustomerUpdate, actor):
        customer = await self.repo.get(company_id, customer_id, for_update=True)
        if not customer:
            raise HTTPException(404, "Customer not found")
        values = data.model_dump(exclude_unset=True)
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
            if key in {"name", "phone", "email", "address"}:
                value = self.clean(value)
            setattr(customer, key, value)
        self.repo.db.add(AuditEvent(company_id=company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="customer_updated", details={"customer_id": str(customer.id)}))
        await self.repo.save(customer)
        return self.view(customer, await self.repo.balance(company_id, customer.id))

    async def history(self, company_id, customer_id):
        if not await self.repo.get(company_id, customer_id):
            raise HTTPException(404, "Customer not found")
        return await self.repo.history(company_id, customer_id)
