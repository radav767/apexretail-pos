"""Test-only debt-first split refunds, frozen original currency budgets, no providers."""
from decimal import Decimal
from uuid import UUID,uuid5,NAMESPACE_URL
from fastapi import Depends,HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from app.models import SaleTender,SaleTenderRefund,Device,AuditEvent,CreditSettlement,CreditRefundAdjustment
from app.accounting.planning import refunds
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.workflows.core import WorkflowService
from .repository import SalesRepository
from .schema import SaleOut
from .split_schema import SplitRefundCreate
from .split import router,require_test_mode

class SplitRefundRepository(SalesRepository):
    split_refund_capable=True
    def __init__(self,db):super().__init__(db,commit_on_save=False);self.allocations=None
    async def begin_refund_command(self,data,actor):
        if not isinstance(data,SplitRefundCreate):raise HTTPException(422,'Versioned split refund input required')
        result,proof=await super().begin_refund_command(data,actor)
        if result:return result,proof
        require_test_mode()
        device=await self.db.get(Device,data.device_id,populate_existing=True)
        if not device or device.company_id!=data.company_id or device.assignment_revision!=data.assignment_revision:raise HTTPException(403,'Original refund register revision changed')
        return None,proof
    async def prepare_split_refund(self,data,original,total):
        if total!=data.expected_total:raise HTTPException(409,'Original item refund differs from expected total')
        legs=(await self.db.execute(select(SaleTender).where(SaleTender.sale_id==original.id,SaleTender.company_id==data.company_id).order_by(SaleTender.id))).scalars().all()
        if not 2<=len(legs)<=20 or sum((r.applied_base for r in legs),Decimal(0))!=original.total_amount:raise HTTPException(409,'Original tender evidence requires review')
        recv=await self.credit_receivable_for_update(data.company_id,original.id)
        credit=sum((r.applied_base for r in legs if r.method=='credit'),Decimal(0))
        if credit and (not recv or recv.original_amount!=credit):raise HTTPException(409,'Original credit evidence requires review')
        sums=(await self.db.execute(select(SaleTenderRefund.tender_id,func.sum(SaleTenderRefund.amount_base),func.sum(SaleTenderRefund.amount_original)).where(SaleTenderRefund.tender_id.in_([r.id for r in legs])).group_by(SaleTenderRefund.tender_id))).all()
        used={key:(base,orig) for key,base,orig in sums}
        if not credit and recv:raise HTTPException(409,'Unexpected original debt projection requires review')
        if recv:
            collected=(await self.db.execute(select(func.coalesce(func.sum(CreditSettlement.amount),0)).where(CreditSettlement.receivable_id==recv.id,CreditSettlement.company_id==data.company_id))).scalar_one()
            credited=(await self.db.execute(select(func.coalesce(func.sum(CreditRefundAdjustment.amount),0)).where(CreditRefundAdjustment.receivable_id==recv.id,CreditRefundAdjustment.company_id==data.company_id))).scalar_one()
            allocated_credit=sum((used.get(r.id,(0,0))[0] for r in legs if r.method=='credit'),Decimal(0))
            if collected!=recv.amount_settled or credited!=recv.amount_credited or credited!=allocated_credit or recv.original_amount-collected-credited!=recv.outstanding_balance:raise HTTPException(409,'Original collection/credit allocation proof differs; retain for review')
        plan=refunds(total,2,[{'id':r.id,'method':r.method,'places':r.currency_places,'applied_base':r.applied_base,'original':r.applied_original,'refunded_base':used.get(r.id,(0,0))[0],'refunded_original':used.get(r.id,(0,0))[1]} for r in legs],recv.outstanding_balance if recv else Decimal(0))
        expected={str(r.tender_id):(r.kind,r.amount_base,r.amount_original) for r in data.allocations}
        actual={r['id']:(r['kind'],Decimal(r['base']),Decimal(r['original'])) for r in plan['allocations']}
        if expected!=actual:raise HTTPException(409,'Original refund allocation changed; review debt and original currency budgets')
        self.allocations=[{'id':uuid5(NAMESPACE_URL,'apex:split-refund:'+str(data.request_id)+':'+key),'company_id':data.company_id,'tender_id':UUID(key),'kind':kind,'amount_base':base,'amount_original':orig} for key,(kind,base,orig) in actual.items()]
        return recv,sum((base for kind,base,_ in actual.values() if kind=='debt_reduction'),Decimal(0))
    async def save_sale(self,*args,**kwargs):
        sale=await super().save_sale(*args,**kwargs)
        if not self.allocations:raise HTTPException(409,'Original split refund plan missing')
        await self.save_allocations(sale)
        return sale
    async def save_allocations(self,sale):
        self.db.add_all([SaleTenderRefund(refund_sale_id=sale.id,**r) for r in self.allocations]);await self.db.flush()
        self.db.add(AuditEvent(company_id=sale.company_id,action='synthetic_split_refund_recorded',details={'refund_sale_id':str(sale.id),'allocations':len(self.allocations),'provider_invoked':False}))

async def response(db,sale):
    rows=(await db.execute(select(SaleTenderRefund).where(SaleTenderRefund.refund_sale_id==sale.id,SaleTenderRefund.company_id==sale.company_id).order_by(SaleTenderRefund.tender_id))).scalars().all()
    if not rows:raise HTTPException(409,'Original refund allocation evidence missing; retain for review')
    return {'contract_version':'split-refund-v2','release_enabled':False,'provider_invoked':False,'sale':SaleOut.model_validate(sale).model_dump(mode='json'),'allocations':[{'tender_id':str(r.tender_id),'kind':r.kind,'amount_base':str(r.amount_base),'amount_original':str(r.amount_original)} for r in rows]}

async def create(db,actor,data):
    from .service import SalesService
    try:
        await WorkflowService(db,actor).current_context(data.company_id,data.branch_id)
        sale=await SalesService(SplitRefundRepository(db)).create_refund(data,actor=actor)
        await db.commit();return await response(db,sale)
    except IntegrityError:
        await db.rollback();raise HTTPException(409,'Original refund identities or budgets conflict; nothing new committed') from None
    except Exception:
        await db.rollback();raise

@router.post('/v2/split/refunds')
async def split_refund(data:SplitRefundCreate,db=Depends(get_db),actor=Depends(get_auth_actor)):return await create(db,actor,data)
