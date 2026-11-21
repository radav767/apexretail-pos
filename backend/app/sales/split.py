"""Synthetic-only atomic online cash/credit split checkout; no provider transport."""
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from uuid import UUID
from fastapi import HTTPException,APIRouter,Depends
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from app.models import SaleTender,AuditEvent,CreditReceivable
from app.core.config import get_settings
from app.accounting.planning import tenders,amount
from app.currencies.repository import CurrencyRepository
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.workflows.core import WorkflowService
from .repository import SalesRepository
from .schema import SaleOut
from .split_schema import SplitSaleCreate

def require_test_mode():
    settings=get_settings()
    if settings.app_env!='test' or settings.split_checkout_mode!='test':raise HTTPException(503,'Split checkout is not release-enabled; only explicit synthetic test mode is available')

class SplitRepository(SalesRepository):
    split_capable=True
    def __init__(self,db):super().__init__(db,commit_on_save=False);self.split_plan=None
    async def begin_command(self,data,actor):
        if not isinstance(data,SplitSaleCreate):raise HTTPException(422,"Explicit versioned split input is required")
        result,proof=await super().begin_command(data,actor)
        if result:return result,proof
        require_test_mode()
        # Global stable leg IDs serialize before shift/customer/product locks.
        for key in sorted((leg.id for leg in data.tenders),key=str):
            await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'sale-tender:'+str(key)})
        if (await self.db.execute(select(SaleTender.id).where(SaleTender.id.in_([r.id for r in data.tenders])).limit(1))).first():raise HTTPException(409,'Tender identity already belongs to an original sale')
        return None,proof
    async def prepare_split(self,data,actor,total):
        if total!=data.expected_total:raise HTTPException(409,'Current priced/taxed sale differs from expected split total')
        repo=CurrencyRepository(self.db);base=await repo.base(data.company_id);settings=await repo.settings(data.company_id)
        if not base or base.decimal_places!=2:raise HTTPException(409,'Initial synthetic split checkout requires a two-decimal base currency')
        if settings.currency_config_version!=data.currency_config_version:raise HTTPException(409,'Split currency configuration changed')
        inputs=[];rows=[];base_change=Decimal(0)
        for leg in data.tenders:
            currency=await repo.by_code(data.company_id,leg.currency_code)
            if not currency:raise HTTPException(409,'Tender currency is inactive or unknown')
            rate=Decimal(1);rate_id=None
            if leg.method=='credit' and not currency.is_base:raise HTTPException(409,'Unpaid credit allocation must use base currency')
            if leg.method=='cash' and not currency.cash_accepted:raise HTTPException(409,'Cash is not accepted in this configured currency')
            if not currency.is_base:
                if not settings.multi_currency_enabled:raise HTTPException(409,'Multi-currency tendering is not configured')
                effective=await repo.current_rate(data.company_id,currency.id,datetime.now(timezone.utc))
                if not effective:raise HTTPException(409,'No effective tender exchange rate')
                rate,rate_id=Decimal(effective.foreign_units_per_base),effective.id
            if (leg.exchange_rate_snapshot,leg.exchange_rate_id)!=(rate,rate_id):raise HTTPException(409,'Original tender exchange-rate quote changed')
            amount(leg.applied_original,currency.decimal_places)
            if leg.method=='cash':
                if leg.tendered_original is None:raise HTTPException(422,'Each cash leg needs explicit original tender')
                amount(leg.tendered_original,currency.decimal_places)
            cash_tender=leg.tendered_original if leg.method=='cash' else Decimal(0)
            change=(cash_tender-leg.applied_original) if leg.method=='cash' else Decimal(0)
            inputs.append({'id':leg.id,'method':leg.method,'currency':currency.code,'places':currency.decimal_places,'applied':leg.applied_original,'tendered':cash_tender if leg.method=='cash' else leg.applied_original,'rate':rate,'quoted_base':leg.applied_base})
            base_change+=(change/rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            rows.append({'id':leg.id,'company_id':data.company_id,'method':leg.method,'currency_code':currency.code,'currency_places':currency.decimal_places,'applied_original':leg.applied_original,'tendered_original':cash_tender,'change_original':change,'applied_base':leg.applied_base,'exchange_rate_id':rate_id,'exchange_rate_snapshot':rate,'currency_config_version':settings.currency_config_version})
        plan=tenders(total,2,inputs);credit=Decimal(plan['credit']);paid=total-credit
        self.split_plan={'rows':rows,'credit':credit,'paid':paid,'change_due':base_change,'amount_received':paid+base_change}
        return self.split_plan
    async def save_sale(self,*args,**kwargs):
        sale=await super().save_sale(*args,**kwargs);await self.save_tenders(sale);return sale
    async def save_credit_sale(self,*args,**kwargs):
        sale=await super().save_credit_sale(*args,**kwargs);await self.save_tenders(sale);return sale
    async def save_tenders(self,sale):
        if not self.split_plan:raise HTTPException(409,'Original split allocation plan is missing')
        self.db.add_all([SaleTender(sale_id=sale.id,**row) for row in self.split_plan['rows']]);await self.db.flush()
        self.db.add(AuditEvent(company_id=sale.company_id,action='synthetic_split_sale_recorded',details={'sale_id':str(sale.id),'tender_count':len(self.split_plan['rows']),'credit':str(self.split_plan['credit']),'paid':str(self.split_plan['paid']),'provider_invoked':False}))

async def response(db,sale):
    rows=(await db.execute(select(SaleTender).where(SaleTender.sale_id==sale.id,SaleTender.company_id==sale.company_id).order_by(SaleTender.id))).scalars().all()
    if not rows:raise HTTPException(409,'Original tender evidence is missing; retain sale for review')
    return {'contract_version':'split-v2','release_enabled':False,'acceptance_scope':'synthetic online cash/credit only','sale':SaleOut.model_validate(sale).model_dump(mode='json'),'tenders':[{'id':str(r.id),'method':r.method,'currency_code':r.currency_code,'currency_places':r.currency_places,'applied_original':str(r.applied_original),'tendered_original':str(r.tendered_original),'change_original':str(r.change_original),'applied_base':str(r.applied_base),'exchange_rate_snapshot':str(r.exchange_rate_snapshot),'exchange_rate_id':str(r.exchange_rate_id) if r.exchange_rate_id else None,'currency_config_version':r.currency_config_version} for r in rows]}

async def create(db,actor,data):
    from .service import SalesService
    try:
        await WorkflowService(db,actor).current_context(data.company_id,data.branch_id)
        sale=await SalesService(SplitRepository(db)).create_sale(data,actor=actor)
        await db.commit()
        return await response(db,sale)
    except IntegrityError:
        await db.rollback();raise HTTPException(409,'Original split identities or allocations conflict; no new sale was committed') from None
    except Exception:
        await db.rollback();raise

router=APIRouter(prefix='/sales',tags=['Synthetic versioned split checkout'])
@router.post('/v2/split')
async def split_sale(data:SplitSaleCreate,db=Depends(get_db),actor=Depends(get_auth_actor)):return await create(db,actor,data)
