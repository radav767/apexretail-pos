"""Dated immutable tender flows; one snapshot, independent revenue and debt."""
from datetime import datetime,timezone,timedelta
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import text,select
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.workflows.core import WorkflowService
from app.printing.service import permit
from app.financial_access import enforce_actor_branch
from app.models import Branch,CashierShift

SQL=text('''
WITH scoped_sales AS (SELECT * FROM sales WHERE company_id=:company AND created_at>=:start AND created_at<:end
 AND (CAST(:branch AS uuid) IS NULL OR branch_id=CAST(:branch AS uuid)) AND (CAST(:shift AS uuid) IS NULL OR shift_id=CAST(:shift AS uuid))),
scoped_collections AS (SELECT * FROM credit_settlements WHERE company_id=:company AND received_at>=:start AND received_at<:end
 AND (CAST(:branch AS uuid) IS NULL OR branch_id=CAST(:branch AS uuid)) AND (CAST(:shift AS uuid) IS NULL OR shift_id=CAST(:shift AS uuid))),
raw AS (
 SELECT 'tender:'||t.id event_id,CASE WHEN t.method='credit' THEN 'credit_origination' ELSE 'original_payment' END kind,
 s.id source_id,s.branch_id,s.shift_id,s.created_at occurred_at,s.receipt_number,s.base_currency_code base_code,t.method,t.currency_code,
 CASE WHEN t.method='credit' THEN 0 ELSE t.applied_base END applied_base,CASE WHEN t.method='credit' THEN t.applied_base ELSE 0 END debt_delta,
 CASE WHEN t.method='credit' THEN NULL ELSE t.applied_original END original_net,CASE WHEN t.method='credit' THEN NULL ELSE t.tendered_original END tender,
 CASE WHEN t.method='credit' THEN NULL ELSE t.change_original END change,t.exchange_rate_snapshot rate
 FROM scoped_sales s JOIN sale_tenders t ON t.sale_id=s.id AND t.company_id=s.company_id WHERE s.payment_method='split' AND s.original_sale_id IS NULL
 UNION ALL
 SELECT 'sale:'||s.id,CASE WHEN s.payment_method='credit' THEN 'credit_origination' ELSE 'original_payment' END,
 s.id,s.branch_id,s.shift_id,s.created_at,s.receipt_number,s.base_currency_code,s.payment_method,s.payment_currency_code,
 CASE WHEN s.payment_method='credit' THEN 0 ELSE s.total_amount END,CASE WHEN s.payment_method='credit' THEN s.total_amount ELSE 0 END,
 CASE WHEN s.payment_method='credit' THEN NULL ELSE s.payment_amount_original END,
 CASE WHEN s.payment_method='credit' THEN NULL ELSE COALESCE(s.tendered_amount_original,s.payment_amount_original) END,
 CASE WHEN s.payment_method='credit' THEN NULL ELSE s.change_amount_original END,s.exchange_rate_snapshot
 FROM scoped_sales s WHERE s.original_sale_id IS NULL AND s.payment_method<>'split'
 UNION ALL
 SELECT 'collection:'||c.id,'credit_collection',c.id,c.branch_id,c.shift_id,c.received_at,c.receipt_number,c.base_currency_code,c.payment_method,c.payment_currency_code,
 c.amount,-c.amount,c.original_amount,COALESCE(c.tendered_amount_original,c.original_amount),c.change_amount_original,c.exchange_rate_snapshot FROM scoped_collections c
 UNION ALL
 SELECT 'refund-allocation:'||a.id,CASE WHEN a.kind='debt_reduction' THEN 'debt_reduction' ELSE 'paid_refund' END,
 s.id,s.branch_id,s.shift_id,s.created_at,s.receipt_number,s.base_currency_code,t.method,t.currency_code,
 CASE WHEN a.kind='debt_reduction' THEN 0 ELSE -a.amount_base END,CASE WHEN a.kind='debt_reduction' THEN -a.amount_base ELSE 0 END,
 CASE WHEN a.kind='debt_reduction' THEN NULL ELSE -a.amount_original END,CASE WHEN a.kind='debt_reduction' THEN NULL ELSE -a.amount_original END,
 CASE WHEN a.kind='debt_reduction' THEN NULL ELSE 0 END,t.exchange_rate_snapshot
 FROM scoped_sales s JOIN sale_tender_refunds a ON a.refund_sale_id=s.id AND a.company_id=s.company_id JOIN sale_tenders t ON t.id=a.tender_id AND t.company_id=a.company_id WHERE s.payment_method='split_refund'
 UNION ALL
 SELECT 'refund:'||s.id,CASE WHEN s.payment_method='credit' THEN 'debt_reduction' ELSE 'paid_refund' END,
 s.id,s.branch_id,s.shift_id,s.created_at,s.receipt_number,s.base_currency_code,s.payment_method,s.payment_currency_code,
 CASE WHEN s.payment_method='credit' THEN 0 ELSE s.total_amount END,CASE WHEN s.payment_method='credit' THEN -n.amount ELSE 0 END,
 CASE WHEN s.payment_method='credit' THEN NULL ELSE -abs(s.payment_amount_original) END,CASE WHEN s.payment_method='credit' THEN NULL ELSE -abs(s.payment_amount_original) END,
 CASE WHEN s.payment_method='credit' THEN NULL ELSE 0 END,s.exchange_rate_snapshot
 FROM scoped_sales s LEFT JOIN credit_refund_adjustments n ON n.refund_sale_id=s.id AND n.company_id=s.company_id WHERE s.original_sale_id IS NOT NULL AND s.payment_method<>'split_refund'
), converted AS (
 SELECT *, (currency_code IS NOT NULL AND original_net IS NOT NULL AND tender IS NOT NULL AND change IS NOT NULL AND tender-change=original_net) original_units_known,
 CASE WHEN method='cash' AND rate>0 THEN round(original_net/rate,2) END converted_net,
 CASE WHEN method='cash' AND rate>0 THEN round(tender/rate,2) END converted_tender,
 CASE WHEN method='cash' AND rate>0 THEN round(change/rate,2) END converted_change,
 (base_code IS NULL OR method NOT IN ('cash','credit','card','mobile') OR (method='credit' AND debt_delta IS NULL) OR
 (method<>'credit' AND (currency_code IS NULL OR original_net IS NULL OR rate IS NULL OR rate<=0 OR tender IS NULL OR change IS NULL OR tender-change<>original_net))) unknown_provenance
 FROM raw
), events AS (SELECT *,CASE WHEN method='cash' THEN applied_base-converted_net END allocation_variance,
 CASE WHEN method='cash' THEN converted_tender-converted_change-converted_net END tender_change_variance,
 CASE WHEN method='cash' THEN converted_tender-converted_change END drawer_valuation FROM converted),
page AS (SELECT * FROM events ORDER BY occurred_at,event_id LIMIT :limit OFFSET :offset),
costs AS (SELECT i.sale_id,sum(i.line_cost) cost,count(*) FILTER(WHERE i.line_cost IS NULL) unknown FROM sale_items i JOIN scoped_sales s ON s.id=i.sale_id GROUP BY i.sale_id),
revenue AS (SELECT s.base_currency_code base_code,count(*) receipts,sum(s.total_amount) billed,sum(s.tax_amount) tax,sum(c.cost) cost,
 count(*) FILTER(WHERE c.cost IS NULL OR c.unknown>0) unknown_cost_receipts FROM scoped_sales s LEFT JOIN costs c ON c.sale_id=s.id GROUP BY s.base_currency_code),
totals AS (SELECT base_code,method,count(*) event_count,sum(applied_base) applied_base,sum(debt_delta) debt_delta,sum(drawer_valuation) FILTER(WHERE NOT unknown_provenance) known_drawer_valuation,
 sum(allocation_variance) FILTER(WHERE NOT unknown_provenance) known_allocation_variance,sum(tender_change_variance) FILTER(WHERE NOT unknown_provenance) known_tender_change_variance,count(*) FILTER(WHERE unknown_provenance) unknown_count FROM events GROUP BY base_code,method),
currency_units AS (SELECT currency_code,count(*) event_count,sum(tender) FILTER(WHERE original_units_known) known_tender,sum(change) FILTER(WHERE original_units_known) known_change,sum(original_net) FILTER(WHERE original_units_known) known_net,
 count(*) FILTER(WHERE NOT original_units_known) unknown_count FROM events WHERE method='cash' GROUP BY currency_code)
SELECT (SELECT count(*) FROM events) event_count,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object('event_id',event_id,'kind',kind,'source_id',source_id,'branch_id',branch_id,'shift_id',shift_id,'occurred_at',occurred_at,'receipt_number',receipt_number,
 'base_code',base_code,'method',method,'currency_code',currency_code,'applied_base',applied_base::text,'debt_delta',debt_delta::text,'original_net',original_net::text,'tender',tender::text,'change',change::text,'rate',rate::text,
 'converted_net',converted_net::text,'converted_tender',converted_tender::text,'converted_change',converted_change::text,'allocation_variance',allocation_variance::text,'tender_change_variance',tender_change_variance::text,
 'drawer_valuation',drawer_valuation::text,'unknown_provenance',unknown_provenance,'original_units_known',original_units_known) ORDER BY occurred_at,event_id),'[]'::jsonb) FROM page) events,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object('base_code',base_code,'method',method,'event_count',event_count,'applied_base',applied_base::text,'debt_delta',debt_delta::text,'known_drawer_valuation',known_drawer_valuation::text,
 'known_allocation_variance',known_allocation_variance::text,'known_tender_change_variance',known_tender_change_variance::text,'unknown_count',unknown_count) ORDER BY base_code,method),'[]'::jsonb) FROM totals) totals,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object('currency_code',currency_code,'event_count',event_count,'known_tender',known_tender::text,'known_change',known_change::text,'known_net',known_net::text,'unknown_count',unknown_count) ORDER BY currency_code),'[]'::jsonb) FROM currency_units) cash_original_units,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object('base_code',base_code,'receipts',receipts,'billed',billed::text,'tax',tax::text,'cost',cost::text,'unknown_cost_receipts',unknown_cost_receipts) ORDER BY base_code),'[]'::jsonb) FROM revenue) revenue
''')

async def authorized_scope(db,actor,company,start,end,branch=None,shift=None):
    if start.tzinfo is None or end.tzinfo is None or not timedelta(0)<end-start<=timedelta(days=366):
        raise HTTPException(422,'Use aware half-open bounds up to366 days')
    await WorkflowService(db,actor).current_context(company)
    permit(actor,'revenue_view');permit(actor,'credit_settlements')
    if actor.employee and actor.role not in {'owner','administrator'}:branch=branch or actor.employee.branch_id
    if shift:
        row=(await db.execute(select(CashierShift.branch_id).where(CashierShift.id==shift,CashierShift.company_id==company))).scalar_one_or_none()
        if not row:raise HTTPException(404,'Shift not found')
        enforce_actor_branch(actor,row)
        if branch and branch!=row:raise HTTPException(403,'Shift branch differs')
        branch=row
    if branch:
        enforce_actor_branch(actor,branch)
        if not (await db.execute(select(Branch.id).where(Branch.company_id==company,Branch.id==branch))).scalar_one_or_none():raise HTTPException(404,'Branch not found')
    start,end=start.astimezone(timezone.utc),end.astimezone(timezone.utc)
    return {'company':company,'branch':branch,'shift':shift,'start':start,'end':end}

async def report(db,actor,company,start,end,branch=None,shift=None,limit=100,offset=0):
    if not 1<=limit<=200 or offset<0:raise HTTPException(422,'Use bounded pagination')
    params=await authorized_scope(db,actor,company,start,end,branch,shift)
    start,end=params['start'],params['end']
    result=dict((await db.execute(SQL,{**params,'limit':limit,'offset':offset})).mappings().one())
    return {'contract_version':'tender-flows-v1','start_inclusive':start.isoformat(),'end_exclusive':end.isoformat(),'read_consistency':'single_statement','limit':limit,'offset':offset,
        'scope':'dated recorded payments/debt and billed revenue; known frozen-rate valuation is not current cash value or provider confirmation','posting_enabled':False,'provider_confirmed':False,**result}

router=APIRouter(prefix='/reports',tags=['Dated tender accounting'])
@router.get('/tender-flows/{company_id}')
async def read(company_id:UUID,start:datetime,end:datetime,branch_id:UUID|None=None,shift_id:UUID|None=None,limit:int=Query(default=100,ge=1,le=200),offset:int=Query(default=0,ge=0),db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await report(db,actor,company_id,start,end,branch_id,shift_id,limit,offset)

@router.get('/reconciliation/{company_id}/export.zip')
async def export_reconciliation(company_id:UUID,start:datetime,end:datetime,branch_id:UUID|None=None,shift_id:UUID|None=None,db=Depends(get_db),actor=Depends(get_auth_actor)):
    from app.accounting.exports import export_bundle
    return await export_bundle(db,actor,company_id,start,end,branch_id,shift_id)
