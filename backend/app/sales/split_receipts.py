"""Receipt disclosure uses original immutable allocations, never current debt/rates."""
from decimal import Decimal
from sqlalchemy import select
from fastapi import HTTPException
from app.models import SaleTender,SaleTenderRefund

async def snapshot(db,sale):
    if sale.payment_method not in {'split','split_refund'}:return None
    legs=[]
    if sale.payment_method=='split':
        rows=(await db.execute(select(SaleTender).where(SaleTender.sale_id==sale.id,SaleTender.company_id==sale.company_id).order_by(SaleTender.id))).scalars().all()
        for row in rows:
            legs.append({'id':str(row.id),'kind':'unpaid_credit' if row.method=='credit' else 'cash_payment','method':row.method,'currency_code':row.currency_code,'currency_places':row.currency_places,
                'applied_base':str(row.applied_base),'applied_original':str(row.applied_original),'tendered_original':str(row.tendered_original) if row.method=='cash' else None,'change_original':str(row.change_original) if row.method=='cash' else None,
                'rate':str(row.exchange_rate_snapshot),'currency_config_version':row.currency_config_version})
        if not 2<=len(legs)<=20:raise HTTPException(409,'Original split receipt tender evidence requires review')
    else:
        rows=(await db.execute(select(SaleTenderRefund,SaleTender).join(SaleTender,SaleTender.id==SaleTenderRefund.tender_id).where(SaleTenderRefund.refund_sale_id==sale.id,SaleTenderRefund.company_id==sale.company_id,SaleTender.company_id==sale.company_id,SaleTender.sale_id==sale.original_sale_id).order_by(SaleTender.id))).all()
        for adjustment,row in rows:
            legs.append({'id':str(row.id),'kind':'debt_reduction' if adjustment.kind=='debt_reduction' else 'cash_refund','method':row.method,'currency_code':row.currency_code,'currency_places':row.currency_places,
                'applied_base':str(adjustment.amount_base),'applied_original':str(adjustment.amount_original),'tendered_original':None,'change_original':None,'rate':str(row.exchange_rate_snapshot),'currency_config_version':row.currency_config_version})
        if not 1<=len(legs)<=20:raise HTTPException(409,'Original split refund receipt allocation requires review')
    if sum((Decimal(r['applied_base']) for r in legs),Decimal(0))!=abs(sale.total_amount):raise HTTPException(409,'Original split receipt allocation sum differs; retain for review')
    refund=sale.payment_method=='split_refund';base=sale.base_currency_code
    def money(value,places,code):
        number=Decimal(value);quantum=Decimal(1).scaleb(-places)
        if number!=number.quantize(quantum):raise HTTPException(409,'Original receipt currency precision requires review')
        return format(number,f'.{places}f')+' '+code
    disclosure=[['Payment','SPLIT REFUND' if refund else 'SPLIT'],['Scope','Recorded accounting only']]
    for leg in legs:
        cash=leg['method']=='cash';code,places=leg['currency_code'],leg['currency_places']
        disclosure.append(['Cash refund' if refund and cash else 'Cash payment' if cash else 'Debt reduction' if refund else 'Original unpaid credit',money(leg['applied_original'],places,code)])
        disclosure.append(['Base reversal' if refund else 'Applied base',money(leg['applied_base'],2,base)])
        if cash and not refund:disclosure.extend([['Tendered',money(leg['tendered_original'],places,code)],['Change',money(leg['change_original'],places,code)]])
        if cash and code!=base:disclosure.append(['Rate 1 '+base,leg['rate']+' '+code])
    return {'version':'split-receipt-v2','scope':'recorded accounting only','provider_confirmed':False,'original_sale_id':str(sale.original_sale_id) if sale.original_sale_id else None,'base_code':base,'legs':legs,'rows':disclosure}
