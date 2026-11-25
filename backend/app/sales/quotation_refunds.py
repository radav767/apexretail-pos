"""Cumulative original-currency returns for immutable accepted quotation sales."""
from decimal import Decimal,ROUND_HALF_UP
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select
from app.models import CommerceOrder,Sale

async def currency(db,original,data,total):
    plan=(await db.execute(select(CommerceOrder.quotation_terms).where(CommerceOrder.company_id==original.company_id,CommerceOrder.sale_id==original.id,CommerceOrder.quotation_terms['version'].as_integer()==2))).scalar_one_or_none()
    if not plan:return None
    method=original.payment_method
    code=original.payment_currency_code if method=='cash' else original.base_currency_code
    if not data.request_id or data.refund_method not in (None,method) or data.payment_currency_code and data.payment_currency_code.strip().upper()!=code:
        raise HTTPException(409,'Saved quotation refunds require identified original-method/currency allocations')
    if method=='credit':
        return {'base_currency':SimpleNamespace(code=original.base_currency_code),'currency':SimpleNamespace(code=code),'exchange_rate_id':None,'exchange_rate_snapshot':Decimal(1),'original_amount':total}
    if method!='cash' or total<=0 or original.total_amount<=0 or not original.payment_amount_original or original.payment_amount_original<=0:
        raise HTTPException(409,'Original quotation payment evidence requires review')
    old=(await db.execute(select(Sale).where(Sale.company_id==original.company_id,Sale.original_sale_id==original.id))).scalars().all()
    if any(r.payment_method!=method or r.payment_currency_code!=code or r.base_currency_code!=original.base_currency_code or r.exchange_rate_snapshot!=original.exchange_rate_snapshot or r.exchange_rate_id!=original.exchange_rate_id or r.payment_amount_original is None or r.payment_amount_original>=0 or r.total_amount>=0 for r in old):
        raise HTTPException(409,'Previous quotation refund evidence requires review')
    base_used=sum((-r.total_amount for r in old),Decimal(0));used=sum((-r.payment_amount_original for r in old),Decimal(0))
    budget=Decimal(original.payment_amount_original);base=Decimal(original.total_amount)
    places=plan['display_places'];quantum=Decimal(1).scaleb(-places)
    if used!=(budget*base_used/base).quantize(quantum,rounding=ROUND_HALF_UP) or base_used+total>base:
        raise HTTPException(409,'Cumulative quotation refund budget requires review')
    target=budget if base_used+total==base else (budget*(base_used+total)/base).quantize(quantum,rounding=ROUND_HALF_UP)
    take=target-used
    if take<=0 or take>budget-used:raise HTTPException(409,'Refund is below original currency minor-unit payout; review allocation')
    return {'base_currency':SimpleNamespace(code=original.base_currency_code),'currency':SimpleNamespace(code=code),'exchange_rate_id':original.exchange_rate_id,'exchange_rate_snapshot':original.exchange_rate_snapshot,'original_amount':take}
