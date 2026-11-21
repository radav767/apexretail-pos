"""Read-only proposed pricing; accepted v1 quotation/checkout gates stay closed."""
from datetime import datetime,timezone
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel,Field,ConfigDict
from fastapi import HTTPException
from sqlalchemy import select,func
from app.models import Product,ProductVariant,CompanySetting,Customer,ProductPriceLevel
from app.accounting.planning import pricing,money,amount
from app.currencies.repository import CurrencyRepository
from app.currencies.service import quantize_currency
from app.printing.service import permit

class ReviewLine(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id:UUID
    quantity:Decimal=Field(gt=0,max_digits=12,decimal_places=3)
    unit:str=Field(min_length=1,max_length=20)
    discount:Decimal=Field(default=0,ge=0,max_digits=16,decimal_places=4)
class PricingReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    lines:list[ReviewLine]=Field(min_length=1,max_length=500)
    sale_discount:Decimal=Field(default=0,ge=0,max_digits=16,decimal_places=4)
    currency_code:str|None=Field(default=None,min_length=3,max_length=8)

async def review(svc,order_id,data):
    from app.sales.commands import actor_identity
    actor_identity(svc.actor,svc.actor.company_id)
    row=await svc.order(order_id);permit(svc.actor,'quotations_manage')
    if row.kind!='quotation' or row.version!=data.version:raise HTTPException(409,'Pricing review needs the current quotation version')
    if any(line.discount for line in data.lines) or data.sale_discount:permit(svc.actor,'sales_discount')
    original={item.id:item for item in await svc.order_items(row) if item.quantity>0}
    if len({line.item_id for line in data.lines})!=len(data.lines) or set(original)!={line.item_id for line in data.lines}:raise HTTPException(422,'Review must identify every current positive quotation position exactly once')
    repo=CurrencyRepository(svc.db);base=await repo.base(row.company_id);settings=await repo.settings(row.company_id)
    if not base or not settings:raise HTTPException(409,'Configured currency/tax policy is required')
    customer=await svc.db.get(Customer,row.customer_id) if row.customer_id else None
    if customer and (not customer.active or customer.deleted or customer.company_id!=row.company_id):raise HTTPException(409,'Quotation customer requires review')
    prepared=[];dimensions={};quantities={}
    for line in data.lines:
        item=original[line.item_id];p=await svc.db.get(Product,item.product_id,populate_existing=True)
        if not p or p.company_id!=row.company_id or not p.active or p.deleted:raise HTTPException(409,'Active tenant product required')
        v=await svc.db.get(ProductVariant,item.variant_id,populate_existing=True) if item.variant_id else None
        if item.variant_id and (not v or v.company_id!=row.company_id or v.product_id!=p.id or not v.active or v.deleted):raise HTTPException(409,'Quotation variant requires review')
        unit=line.unit.strip().lower()
        if unit==p.unit:factor=Decimal(1)
        elif unit==str(p.purchase_unit or '').strip().lower():factor=Decimal(p.units_per_purchase or 0)
        else:raise HTTPException(422,'Custom unit must match configured base/purchase unit; no inferred conversion')
        if factor<=0:raise HTTPException(409,'Configured unit conversion is unavailable')
        dimensions[line.item_id]=(p,v,factor);key=(p.id,item.variant_id);quantities[key]=quantities.get(key,Decimal(0))+line.quantity*factor
    for line in data.lines:
        item=original[line.item_id];p,v,factor=dimensions[line.item_id]
        level=(await svc.db.execute(select(ProductPriceLevel).where(ProductPriceLevel.company_id==row.company_id,ProductPriceLevel.product_id==p.id,func.lower(ProductPriceLevel.name)==customer.price_level_name.lower(),ProductPriceLevel.minimum_quantity<=quantities[(p.id,item.variant_id)],ProductPriceLevel.active.is_(True),ProductPriceLevel.deleted.is_(False)).order_by(ProductPriceLevel.minimum_quantity.desc()).limit(1))).scalar_one_or_none() if customer and customer.price_level_name else None
        price=level.price if level else v.selling_price if v and v.selling_price is not None else p.selling_price
        if price is None:raise HTTPException(409,'Configured price is unavailable')
        prepared.append({'id':line.item_id,'quantity':line.quantity,'factor':factor,'price':price,'discount':line.discount,'tax_rate':0 if p.tax_exempt else p.tax_rate if p.tax_rate is not None else settings.tax_rate or 0})
    result=pricing(prepared,base.decimal_places,settings.tax_inclusive,data.sale_discount)
    currency=await repo.by_code(row.company_id,(data.currency_code or base.code).strip().upper())
    if not currency:raise HTTPException(409,'Requested display currency is inactive or unknown')
    rate=Decimal(1);rate_id=None
    if not currency.is_base:
        if not settings.multi_currency_enabled:raise HTTPException(409,'Multi-currency review is not configured')
        rate_row=await repo.current_rate(row.company_id,currency.id,datetime.now(timezone.utc))
        if not rate_row:raise HTTPException(409,'No effective display currency rate')
        rate=Decimal(rate_row.foreign_units_per_base);rate_id=str(rate_row.id)
    return {**result,'order_id':str(row.id),'version':row.version,'base_currency':base.code,'display_currency':currency.code,'display_total':str(quantize_currency(Decimal(result['total'])*rate,currency.decimal_places)),'exchange_rate_snapshot':str(rate),'exchange_rate_id':rate_id,'currency_config_version':settings.currency_config_version,'accepted_terms_changed':False,'conversion_enabled':False,'contract':'pricing-review-v2; not a posted sale or accepted quotation'}
