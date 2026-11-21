"""Historical original-leg disclosure; never regenerates saved receipt/document bytes."""
from uuid import UUID
from decimal import Decimal
from fastapi import Depends,HTTPException,Query
from sqlalchemy import text,select
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.workflows.core import WorkflowService
from app.models import Sale
from app.financial_access import enforce_actor_branch
from app.employees.permissions import has_permission
from .split import router

# Each ledger is aggregated independently. Monetary JSON values are text, not
# JSON floats. One SQL snapshot owns all equations, totals and the history page.
STATEMENT=text('''
WITH original AS (SELECT * FROM sales WHERE id=:original AND company_id=:company),
allocations AS (SELECT r.* FROM sale_tender_refunds r JOIN sale_tenders t ON t.id=r.tender_id JOIN original o ON o.id=t.sale_id WHERE r.company_id=o.company_id),
used AS (SELECT tender_id,sum(amount_base) base,sum(amount_original) original FROM allocations GROUP BY tender_id),
legs AS (SELECT t.*,COALESCE(u.base,0) refunded_base,COALESCE(u.original,0) refunded_original FROM sale_tenders t JOIN original o ON o.id=t.sale_id LEFT JOIN used u ON u.tender_id=t.id),
receivable AS (SELECT r.* FROM credit_receivables r JOIN original o ON o.id=r.sale_id AND o.company_id=r.company_id),
collections AS (SELECT s.* FROM credit_settlements s JOIN receivable r ON r.id=s.receivable_id AND r.company_id=s.company_id),
notes AS (SELECT n.* FROM credit_refund_adjustments n JOIN receivable r ON r.id=n.receivable_id AND r.company_id=n.company_id),
refunds AS (SELECT s.* FROM sales s JOIN original o ON o.id=s.original_sale_id AND o.company_id=s.company_id WHERE s.payment_method='split_refund'),
visible_refunds AS (SELECT * FROM refunds WHERE CAST(:branch AS uuid) IS NULL OR branch_id=CAST(:branch AS uuid)),
history AS (SELECT * FROM visible_refunds ORDER BY created_at,id LIMIT :limit OFFSET :offset)
SELECT o.id,o.receipt_number,o.base_currency_code,o.total_amount,o.tax_amount,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object('id',id,'method',method,'currency_code',currency_code,'currency_places',currency_places,
 'applied_base',applied_base::text,'applied_original',applied_original::text,'tendered_original',tendered_original::text,'change_original',change_original::text,
 'exchange_rate_id',exchange_rate_id,'exchange_rate_snapshot',exchange_rate_snapshot::text,'currency_config_version',currency_config_version,
 'refunded_base',refunded_base::text,'refunded_original',refunded_original::text,'remaining_base',(applied_base-refunded_base)::text,'remaining_original',(applied_original-refunded_original)::text) ORDER BY id),'[]'::jsonb) FROM legs) legs,
 (SELECT count(*) FROM visible_refunds) refund_count,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object('id',h.id,'receipt_number',h.receipt_number,'branch_id',h.branch_id,'created_at',h.created_at,'total_amount',h.total_amount::text,'tax_amount',h.tax_amount::text,
 'allocations',(SELECT COALESCE(jsonb_agg(jsonb_build_object('tender_id',a.tender_id,'kind',a.kind,'amount_base',a.amount_base::text,'amount_original',a.amount_original::text) ORDER BY a.tender_id),'[]'::jsonb) FROM allocations a WHERE a.refund_sale_id=h.id)) ORDER BY h.created_at,h.id),'[]'::jsonb) FROM history h) history,
 (SELECT COALESCE(sum(applied_base),0) FROM legs WHERE method='cash') initial_cash,
 (SELECT COALESCE(sum(applied_base),0) FROM legs WHERE method='credit') original_credit,
 (SELECT COALESCE(sum(amount_base),0) FROM allocations WHERE kind='paid_refund') cash_refunded,
 (SELECT COALESCE(sum(amount_base),0) FROM allocations WHERE kind='debt_reduction') debt_reduced,
 (SELECT COALESCE(sum(amount_base),0) FROM allocations) refund_allocated,
 (SELECT COALESCE(sum(-total_amount),0) FROM refunds) refund_total,
 (SELECT COALESCE(sum(tax_amount),0) FROM refunds) refund_tax,
 (SELECT COALESCE(sum(amount),0) FROM collections) collected,
 (SELECT COALESCE(sum(amount),0) FROM notes) credited,
 (SELECT COALESCE(sum(amount_settled),0) FROM receivable) projected_collected,
 (SELECT COALESCE(sum(amount_credited),0) FROM receivable) projected_credited,
 (SELECT COALESCE(sum(outstanding_balance),0) FROM receivable) outstanding
FROM original o
''')

async def history(db,actor,company,sale_id,limit=100,offset=0):
    if not 1<=limit<=100 or offset<0:raise HTTPException(422,'Invalid bounded history page')
    await WorkflowService(db,actor).current_context(company)
    # Same native historical-receipt permissions, without materializing its
    # entire lifetime item/refund history before the bounded ledger query.
    if actor.actor_type=='employee' and not any(has_permission(actor.permissions or {},key) for key in ('sales_history_view','sales_refund')):raise HTTPException(403,'Permission denied')
    selected=(await db.execute(select(Sale.id,Sale.original_sale_id,Sale.branch_id,Sale.payment_method).where(Sale.id==sale_id,Sale.company_id==company))).mappings().one_or_none()
    if not selected:raise HTTPException(404,'Sale not found')
    enforce_actor_branch(actor,selected['branch_id'])
    if selected['payment_method'] not in {'split','split_refund'}:raise HTTPException(409,'This receipt has no versioned split accounting contract')
    original=selected['original_sale_id'] or selected['id']
    if original!=selected['id']:
        # A cross-branch return does not grant access to the original branch.
        original_branch=(await db.execute(select(Sale.branch_id).where(Sale.id==original,Sale.company_id==company))).scalar_one_or_none()
        if not original_branch:raise HTTPException(409,'Original sale branch evidence missing')
        enforce_actor_branch(actor,original_branch)
    branch=actor.employee.branch_id if actor.employee and actor.role not in {'owner','administrator'} else None
    row=(await db.execute(STATEMENT,{'original':original,'company':company,'limit':limit,'offset':offset,'branch':branch})).mappings().one_or_none()
    if not row or not 2<=len(row['legs'])<=20:raise HTTPException(409,'Original tender evidence missing; retain for review')
    matches=(sum((Decimal(r['applied_base']) for r in row['legs']),Decimal(0))==row['total_amount'] and row['refund_total']==row['refund_allocated']
        and row['collected']==row['projected_collected'] and row['credited']==row['projected_credited']==row['debt_reduced']
        and row['original_credit']-row['collected']-row['credited']==row['outstanding'])
    return {'contract_version':'split-history-v2','selected_sale_id':str(sale_id),'original_sale_id':str(original),'receipt_number':row['receipt_number'],'base_currency_code':row['base_currency_code'],
        'read_consistency':'single_statement','scope':'original tender accounting and current debt; not historical as-of cash flow or provider confirmation',
        'posting_enabled':False,'provider_confirmed':False,'reprint_recorded':False,'refund_page_scope':'current authorized branches; totals follow original tender budgets','legs':row['legs'],'refunds':row['history'],'refund_count':row['refund_count'],'limit':limit,'offset':offset,
        'totals':{name:str(row[name]) for name in ('total_amount','tax_amount','initial_cash','original_credit','collected','credited','outstanding','cash_refunded','debt_reduced','refund_total','refund_tax')},
        'net_billed':str(row['total_amount']-row['refund_total']),'net_tax':str(row['tax_amount']+row['refund_tax']),
        'net_applied_cash_base':str(row['initial_cash']+row['collected']-row['cash_refunded']),'ledger_matches':matches,'status':'reconciled' if matches else 'provenance_review_required'}

@router.get('/v2/split/history/{company_id}/{sale_id}')
async def read_history(company_id:UUID,sale_id:UUID,limit:int=Query(default=100,ge=1,le=100),offset:int=Query(default=0,ge=0),db=Depends(get_db),actor=Depends(get_auth_actor)):return await history(db,actor,company_id,sale_id,limit,offset)
