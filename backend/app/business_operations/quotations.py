"""Frozen quotations never reserve stock or imply provider/message success."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal,ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select,text,func
from types import SimpleNamespace
from app.models import (QuotationCommand,Device,Product,ProductVariant,CompanySetting,CompanyCurrency,Customer,ProductPriceLevel)
from app.sales.commands import actor_identity,fingerprint
from app.printing.service import permit


async def read_one(db,query):
    model=query.column_descriptions[0]['entity']
    value=(await db.execute(query.with_only_columns(*model.__table__.c))).mappings().one_or_none()
    return SimpleNamespace(**value) if value else None


async def read_many(db,query):
    model=query.column_descriptions[0]['entity']
    return [SimpleNamespace(**value) for value in (await db.execute(query.with_only_columns(*model.__table__.c))).mappings()]


def state(row):
    if row.status=='settled':return 'converted' if row.quotation_terms else 'legacy_converted'
    if row.quotation_status in {'sent','accepted'} and row.quotation_valid_until and row.quotation_valid_until<=datetime.now(timezone.utc):return 'expired'
    return row.quotation_status or 'legacy_review'


async def terms(svc,row):
    if row.quotation_pricing:
        from .saved_pricing import frozen
        return await frozen(svc,row,draft=True)
    db=svc.db
    # Read estimates without acquiring checkout locks ahead of its shift lock.
    # Raw mapping snapshots leave the ORM identity map untouched; checkout
    # refreshes its locking reads and final sale terms are compared before commit.
    customer=await read_one(db,select(Customer).where(Customer.id==row.customer_id,Customer.company_id==row.company_id)) if row.customer_id else None
    if row.customer_id and (not customer or not customer.active or customer.deleted):raise HTTPException(409,'Quotation customer is no longer active')
    device=await read_one(db,select(Device).where(Device.id==row.device_id))
    validate_device(svc,row,device)
    items=[item for item in await svc.order_items(row) if item.quantity>0]
    if not items:raise HTTPException(400,'Quotation is empty')
    products=await read_many(db,select(Product).where(Product.id.in_([i.product_id for i in items]),Product.company_id==row.company_id).order_by(Product.id))
    catalog={p.id:p for p in products};variants={}
    ids=[i.variant_id for i in items if i.variant_id]
    if ids:variants={v.id:v for v in await read_many(db,select(ProductVariant).where(ProductVariant.id.in_(ids),ProductVariant.company_id==row.company_id).order_by(ProductVariant.id))}
    quantities={}
    for item in items:
        key=(item.product_id,item.variant_id);quantities[key]=quantities.get(key,Decimal(0))+item.quantity
    priced=[]
    for item in items:
        product=catalog.get(item.product_id);variant=variants.get(item.variant_id)
        if not product or not product.active or product.deleted or item.variant_id and (not variant or not variant.active or variant.deleted or variant.product_id!=product.id):raise HTTPException(409,'Quotation catalog requires review')
        level=await read_one(db,select(ProductPriceLevel).where(ProductPriceLevel.company_id==row.company_id,ProductPriceLevel.product_id==product.id,func.lower(ProductPriceLevel.name)==customer.price_level_name.lower(),ProductPriceLevel.minimum_quantity<=quantities[(item.product_id,item.variant_id)],ProductPriceLevel.active.is_(True),ProductPriceLevel.deleted.is_(False)).order_by(ProductPriceLevel.minimum_quantity.desc()).limit(1)) if customer and customer.price_level_name else None
        raw_price=level.price if level else variant.selling_price if variant and variant.selling_price is not None else product.selling_price
        if raw_price is None or item.unit!=product.unit:raise HTTPException(409,'Quotation price or unit requires review')
        price=Decimal(raw_price)
        priced.append((item,product,price))
    settings=await read_one(db,select(CompanySetting).where(CompanySetting.company_id==row.company_id,CompanySetting.deleted.is_(False)))
    base=await read_one(db,select(CompanyCurrency).where(CompanyCurrency.company_id==row.company_id,CompanyCurrency.is_base.is_(True)))
    if not settings or not base or base.decimal_places!=2:raise HTTPException(409,'Quotation requires a configured two-decimal base currency')
    output={'version':1,'customer_id':str(row.customer_id) if row.customer_id else None,'customer_price_level':customer.price_level_name if customer else None,
        'currency':base.code,'tax_name':settings.tax_name,'tax_rate':str(Decimal(settings.tax_rate or 0).normalize()),'tax_inclusive':settings.tax_inclusive,'discount':'0.00','items':[]}
    raw=Decimal(0);line_tax=Decimal(0);explicit=False;financial={}
    for item,product,price in priced:
        exempt=bool(product.tax_exempt);rate=Decimal(0) if exempt else Decimal(product.tax_rate if product.tax_rate is not None else settings.tax_rate or 0)
        key=(item.product_id,item.variant_id,item.unit)
        old=financial.get(key,(price,Decimal(0),rate,product.tax_rate is not None or exempt))
        financial[key]=(price,old[1]+item.quantity,rate,old[3])
        output['items'].append({'id':str(item.id),'product_id':str(product.id),'variant_id':str(item.variant_id) if item.variant_id else None,'quantity':str(item.quantity.quantize(Decimal('.001'))),'unit':item.unit,'price':str(price.quantize(Decimal('.01'))),'tax_rate':str(rate.normalize()),'tax_exempt':exempt})
    raw=Decimal(0);line_tax=Decimal(0);explicit=False
    for price,quantity,rate,has_rule in financial.values():
        amount=(price*quantity).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);raw+=amount;explicit|=has_rule
        line_tax+=((amount-amount/(1+rate/100)) if settings.tax_inclusive else amount*rate/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    fraction=Decimal(settings.tax_rate or 0)/100
    tax=line_tax if explicit else ((raw-raw/(1+fraction)) if settings.tax_inclusive else raw*fraction).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    output.update(tax=str(tax),total=str(raw if settings.tax_inclusive else raw+tax))
    return output


def validate_device(svc,row,device,revision=None):
    if (not device or device.company_id!=row.company_id or device.branch_id!=row.branch_id or not device.active or device.deleted or device.removed_at or device.deactivated_at or
        revision is not None and device.assignment_revision!=revision or svc.actor.employee and (not svc.actor.pos_session or svc.actor.pos_session.device_id!=device.id)):
        raise HTTPException(403,'Quotation register is no longer authorized')


async def transition(svc,order_id,data):
    identity=actor_identity(svc.actor,svc.actor.company_id);permit(svc.actor,'quotations_manage')
    from .quotation_revisions import lock_lineage,require_current
    await lock_lineage(svc,order_id)
    await svc.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-quotation:'+str(data.request_id)})
    row=await svc.order(order_id)
    if row.kind!='quotation':raise HTTPException(400,'Quotation workflow requires a quotation')
    device=await svc.db.get(Device,row.device_id,populate_existing=True);validate_device(svc,row,device)
    device_id,revision=device.id,device.assignment_revision
    proof=await svc.db.get(QuotationCommand,data.request_id);command_hash=fingerprint(data)
    if proof:
        if proof.company_id!=row.company_id or proof.order_id!=row.id or proof.payload_hash!=command_hash:raise HTTPException(409,'Quotation command identity has different values')
        if (proof.actor_type,proof.actor_id)!=(svc.actor.actor_type,identity):raise HTTPException(403,'Original quotation action belongs to another actor')
        validate_device(svc,row,device,proof.assignment_revision)
        return {**await svc.order_out(row),'quotation_command_ack':str(data.request_id)}
    await svc.require_write('wholesale')
    if row.status!='open' or row.version!=data.version:raise HTTPException(409,'Quotation changed or locked')
    await require_current(svc,row,conversion=True)
    current=state(row)
    if data.action=='sent':
        deadline=data.valid_until
        now=datetime.now(timezone.utc)
        if current!='draft':raise HTTPException(409,'Only drafts may be sent; create a new draft for revised terms')
        if not deadline or deadline.utcoffset() is None or not now<deadline<=now+timedelta(days=366):raise HTTPException(422,'Quotation requires a future timezone-aware validity within 366 days')
        frozen=await terms(svc,row)
        prices={item['id']:Decimal(item['price']) for item in frozen['items']}
        for item in await svc.order_items(row):
            if str(item.id) in prices:item.price=prices[str(item.id)]
        await svc.db.flush()  # Update draft estimates before freezing their rows.
        row.quotation_terms=frozen;row.quotation_valid_until=deadline
    else:
        if current!='sent' or data.valid_until is not None:raise HTTPException(409,'Only unexpired sent quotations may be accepted or rejected without changing terms')
    row.quotation_status=data.action;row.version+=1
    svc.db.add(QuotationCommand(request_id=data.request_id,company_id=row.company_id,order_id=row.id,actor_type=svc.actor.actor_type,actor_id=identity,
        payload_hash=command_hash,device_id=device_id,assignment_revision=revision,action=data.action))
    svc.audit('quotation_'+data.action,order_id=row.id,request_id=data.request_id)
    await svc.commit_operation()
    return {**await svc.order_out(row),'quotation_command_ack':str(data.request_id)}


async def require_conversion(svc,row,payment):
    from .quotation_revisions import require_current
    await require_current(svc,row,conversion=True)
    if state(row)!='accepted' or not row.quotation_terms:raise HTTPException(409,'Only accepted, unexpired quotations with frozen terms may convert')
    if any(Decimal(getattr(payment,key,None) or 0) for key in ('discount_amount','sale_discount_amount')):raise HTTPException(409,'Quotation discount terms are frozen')
    if row.quotation_terms.get('version')==2:
        from .saved_pricing import frozen
        await frozen(svc,row);return
    if await terms(svc,row)!=row.quotation_terms:raise HTTPException(409,'Quotation terms changed; create and accept a new draft before conversion')


async def validate_sale(svc,row,sale):
    frozen=row.quotation_terms
    if frozen.get('version')==2:
        if sale.total_amount!=Decimal(frozen['total']) or sale.tax_amount!=Decimal(frozen['tax']) or sale.discount_amount!=Decimal(frozen['discount']) or sale.tax_inclusive!=frozen['tax_inclusive'] or sale.tax_name!=frozen['tax_name'] or Decimal(sale.tax_rate)!=Decimal(frozen['tax_rate']) or sale.base_currency_code!=frozen['currency']:raise HTTPException(409,'Accepted pricing differs from final sale')
        if sale.payment_method=='cash' and (sale.payment_currency_code!=frozen['display_currency'] or sale.payment_amount_original!=Decimal(frozen['display_total']) or sale.exchange_rate_snapshot!=Decimal(frozen['exchange_rate_snapshot']) or (str(sale.exchange_rate_id) if sale.exchange_rate_id else None)!=frozen['exchange_rate_id']):
            raise HTTPException(409,'Sale differs from accepted original currency/rounding evidence')
        return
    if (sale.total_amount!=Decimal(frozen['total']) or sale.tax_amount!=Decimal(frozen['tax']) or Decimal(sale.discount_amount or 0)!=0 or
        sale.tax_inclusive!=frozen['tax_inclusive'] or sale.tax_name!=frozen['tax_name'] or Decimal(sale.tax_rate)!=Decimal(frozen['tax_rate']) or sale.base_currency_code!=frozen['currency']):
        raise HTTPException(409,'Sale differs from frozen quotation terms; nothing was posted')
    expected={}
    for item in frozen['items']:
        key=(item['product_id'],item['variant_id'],item['unit'])
        old=expected.get(key,(Decimal(0),Decimal(item['price']),Decimal(item['tax_rate']),item['tax_exempt']))
        expected[key]=(old[0]+Decimal(item['quantity']),*old[1:])
    from app.models import SaleItem
    actual={}
    for item in (await svc.db.execute(select(SaleItem).where(SaleItem.sale_id==sale.id))).scalars():
        actual[(str(item.product_id),str(item.variant_id) if item.variant_id else None,item.selling_unit)]=(Decimal(item.quantity),Decimal(item.unit_price),Decimal(item.tax_rate_snapshot),bool(item.tax_exempt_snapshot))
    if actual!=expected:raise HTTPException(409,'Sale line terms differ from accepted quotation; nothing was posted')
