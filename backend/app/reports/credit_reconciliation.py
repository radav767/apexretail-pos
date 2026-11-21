"""Single-statement current receivable/immutable-ledger proof, never repair."""
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter,Depends,Query,HTTPException
from sqlalchemy import select,func
from app.models import CreditReceivable,CreditSettlement,CreditRefundAdjustment,Branch
from app.auth.dependencies import require_path_permission
from app.db.session import get_db
from app.sales.commands import actor_identity
from app.printing.service import permit
from app.financial_access import enforce_actor_branch

async def reconcile(db,actor,company,branch=None,limit=100,offset=0):
    actor_identity(actor,company);permit(actor,'profits_view');permit(actor,'customers_view');permit(actor,'credit_settlements')
    if not 1<=limit<=100 or offset<0:raise HTTPException(422,'Invalid reconciliation page')
    if actor.employee and actor.role not in {'owner','administrator'}:branch=branch or actor.employee.branch_id
    if branch:
        enforce_actor_branch(actor,branch)
        if not (await db.execute(select(Branch.id).where(Branch.id==branch,Branch.company_id==company))).scalar_one_or_none():raise HTTPException(404,'Branch not found')
    query=select(CreditReceivable).where(CreditReceivable.company_id==company)
    if branch:query=query.where(CreditReceivable.branch_id==branch)
    page=query.order_by(CreditReceivable.id).limit(limit).offset(offset).cte('receivable_page')
    collected=select(CreditSettlement.receivable_id,func.sum(CreditSettlement.amount).label('collected')).where(CreditSettlement.company_id==company,CreditSettlement.receivable_id.in_(select(page.c.id))).group_by(CreditSettlement.receivable_id).subquery()
    credited=select(CreditRefundAdjustment.receivable_id,func.sum(CreditRefundAdjustment.amount).label('credited')).where(CreditRefundAdjustment.company_id==company,CreditRefundAdjustment.receivable_id.in_(select(page.c.id))).group_by(CreditRefundAdjustment.receivable_id).subquery()
    statement=select(page,func.coalesce(collected.c.collected,0).label('ledger_collected'),func.coalesce(credited.c.credited,0).label('ledger_credited')).outerjoin(collected,page.c.id==collected.c.receivable_id).outerjoin(credited,page.c.id==credited.c.receivable_id)
    rows=[]
    for r in (await db.execute(statement)).mappings():
        matches=r['amount_settled']==r['ledger_collected'] and r['amount_credited']==r['ledger_credited']
        projection=r['original_amount']-r['amount_settled']-r['amount_credited']==r['outstanding_balance']
        rows.append({'receivable_id':str(r['id']),'sale_id':str(r['sale_id']),'branch_id':str(r['branch_id']),'currency':r['currency_code'],'original':str(r['original_amount']),'collected':str(r['ledger_collected']),'credited':str(r['ledger_credited']),'outstanding':str(r['outstanding_balance']),'projection_valid':projection,'ledger_matches':matches,'status':'reconciled' if matches and projection else 'provenance_review_required'})
    return {'scope':'current receivable proof; not historical as-of cash flow','read_consistency':'single_statement','repair_performed':False,'limit':limit,'offset':offset,'items':rows}
router=APIRouter(prefix='/reports',tags=['Financial reconciliation evidence'])
@router.get('/credit-reconciliation/{company_id}')
async def evidence(company_id:UUID,branch_id:UUID|None=None,limit:int=Query(default=100,ge=1,le=100),offset:int=Query(default=0,ge=0),db=Depends(get_db),actor=Depends(require_path_permission('profits_view'))):return await reconcile(db,actor,company_id,branch_id,limit,offset)
