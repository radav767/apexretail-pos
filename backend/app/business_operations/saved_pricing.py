"""Versioned saved quotation plan, explicit acceptance and native atomic checkout."""
from decimal import Decimal
from uuid import UUID
from pydantic import Field
from fastapi import HTTPException
from sqlalchemy import select,text
from app.models import QuotationCommand,Product,ProductVariant,CompanySetting,Device,ProductPriceLevel
from app.sales.commands import actor_identity,fingerprint
from app.sales.repository import SalesRepository
from app.sales.schema import SaleItemCreate
from app.printing.service import permit
from app.core.config import get_settings
from .pricing_review import PricingReview,review
from .quotation_revisions import lock_lineage,require_current
from .quotations import validate_device

class SavePricing(PricingReview):
    request_id:UUID
    expected_total:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
    expected_display_total:Decimal=Field(gt=0,max_digits=18,decimal_places=4)

def mode():
    s=get_settings()
    if s.app_env!='test' or s.quotation_pricing_mode!='test':raise HTTPException(503,'Saved quotation pricing is disabled outside explicit synthetic test mode')

async def compute(svc,row,data):
    result=await review(svc,row.id,data,internal=True)
    if result['minor_unit_places']!=2:raise HTTPException(409,'Non-two-decimal base checkout requires separate acceptance')
    lines={item['id']:item for item in result['items']};positions=[];seen=set()
    for p in result['positions']:
        pair=(p['product_id'],p['variant_id'])
        if pair in seen or p['product_type'] not in {'standard','service','non_stock','variable_weight'}:raise HTTPException(409,'Consolidate repeated products; recipe checkout needs separate pricing acceptance')
        seen.add(pair);item={**p,**lines[p['id']]};SaleItemCreate(product_id=p['product_id'],quantity=item['base_quantity'],selling_unit=p['base_unit'],unit_price=p['price'])
        positions.append(item)
    return {'version':2,'items':positions,'currency':result['base_currency'],'display_currency':result['display_currency'],'display_places':result['display_places'],
        **{k:result[k] for k in ('total','tax','subtotal','discount','tax_name','tax_rate','tax_inclusive','display_total','exchange_rate_snapshot','exchange_rate_id','currency_config_version')},
        'sale_discount':str(data.sale_discount),'input':PricingReview.model_validate(data.model_dump(include=set(PricingReview.model_fields))).model_dump(mode='json',exclude={'version'})}

def public_plan(plan):
    if not plan or plan.get('version')!=2:return plan
    return {**plan,'items':[{k:v for k,v in row.items() if k!='cost'} for row in plan['items']]}

async def save(svc,order_id,data):
    try:
        from app.workflows.core import WorkflowService
        await WorkflowService(svc.db,svc.actor).current_context(svc.actor.company_id)
        identity=actor_identity(svc.actor,svc.actor.company_id);permit(svc.actor,'quotations_manage');await lock_lineage(svc,order_id)
        await svc.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-quotation:'+str(data.request_id)})
        row=await svc.order(order_id);device=await svc.db.get(Device,row.device_id,populate_existing=True);validate_device(svc,row,device)
        old=await svc.db.get(QuotationCommand,data.request_id);digest=fingerprint(data)
        if old:
            if old.company_id!=row.company_id or old.order_id!=row.id or old.action!='pricing_saved' or old.payload_hash!=digest:raise HTTPException(409,'Quotation pricing identity differs')
            if (old.actor_type,old.actor_id)!=(svc.actor.actor_type,identity):raise HTTPException(403,'Original pricing belongs to another actor')
            validate_device(svc,row,device,old.assignment_revision);return old.result
        mode();await svc.require_write('wholesale');await require_current(svc,row,conversion=True)
        if row.kind!='quotation' or row.status!='open' or row.quotation_status!='draft' or row.version!=data.version:raise HTTPException(409,'Save pricing only against the current draft version')
        source=await svc.order_items(row)
        for model,ids in ((Product,[r.product_id for r in source]),(ProductVariant,[r.variant_id for r in source if r.variant_id])):
            await svc.db.execute(select(model.id).where(model.company_id==row.company_id,model.id.in_(ids)).order_by(model.id).with_for_update(read=True))
        await svc.db.execute(select(CompanySetting.id).where(CompanySetting.company_id==row.company_id).with_for_update(read=True))
        plan=await compute(svc,row,data)
        if Decimal(plan['total'])!=data.expected_total or Decimal(plan['display_total'])!=data.expected_display_total:raise HTTPException(409,'Pricing expectation changed; review exact totals')
        by_id={r['id']:r for r in plan['items']}
        for item in await svc.order_items(row):
            if item.quantity<=0:continue
            p=by_id[str(item.id)];item.name=p['name'];item.quantity=Decimal(p['base_quantity']);item.unit=p['base_unit'];item.price=Decimal(p['price'])
        row.version+=1;plan['bound_version']=row.version;row.quotation_pricing=plan
        result={'order_id':str(row.id),'version':row.version,'quotation_pricing':public_plan(plan),'quotation_command_ack':str(data.request_id)}
        svc.db.add(QuotationCommand(request_id=data.request_id,company_id=row.company_id,order_id=row.id,actor_type=svc.actor.actor_type,actor_id=identity,payload_hash=digest,device_id=device.id,assignment_revision=device.assignment_revision,action='pricing_saved',result=result))
        svc.audit('quotation_pricing_saved',order_id=row.id,request_id=data.request_id);await svc.commit_operation();return result
    except Exception:await svc.db.rollback();raise

async def frozen(svc,row,draft=False):
    mode();plan=row.quotation_pricing
    if draft and plan['bound_version']!=row.version:raise HTTPException(409,'Draft edits invalidate saved pricing; explicitly resave')
    data=PricingReview.model_validate({**plan['input'],'version':row.version});current=await compute(svc,row,data)
    # Additive tier-label evidence applies to new plans. Never rewrite older
    # accepted v2 plans or invent a missing historical label.
    old_items={r['id']:r for r in plan['items']}
    for item in current['items']:
        for field in ('price_level_name','track_inventory'):
            if field not in old_items[item['id']]:item.pop(field,None)
    if {k:v for k,v in plan.items() if k!='bound_version'}!=current:raise HTTPException(409,'Configured pricing/unit/currency/cost changed; revise and accept again')
    return plan

def payment(row,payment):
    mode();p=row.quotation_terms
    if payment.payment_method not in {'cash','credit'}:raise HTTPException(409,'Saved quote acceptance covers cash/credit only')
    if payment.payment_method=='cash' and payment.payment_currency_code not in (None,p['display_currency']):raise HTTPException(409,'Use accepted quotation payment currency')
    from app.currencies.service import quantize_currency
    tender=payment.tendered_amount_original if payment.tendered_amount_original is not None else payment.amount_received if p['display_currency']==p['currency'] else None
    if payment.payment_method=='cash' and tender is not None and quantize_currency(tender,p['display_places'])!=tender:raise HTTPException(422,'Cash tender exceeds accepted original currency precision')
    return payment.model_copy(update={'items':[SaleItemCreate(product_id=r['product_id'],variant_id=r['variant_id'],quantity=r['base_quantity'],selling_unit=r['base_unit'],unit_price=r['price'],line_total=r['net'],line_discount_amount=r['line_discount']) for r in p['items']],
        'discount_amount':Decimal(p['discount']),'sale_discount_amount':Decimal(p['sale_discount']),
        'payment_currency_code':p['display_currency'] if payment.payment_method=='cash' else p['currency'],'exchange_rate_id':UUID(p['exchange_rate_id']) if p['exchange_rate_id'] and payment.payment_method=='cash' else None,
        'exchange_rate_snapshot':Decimal(p['exchange_rate_snapshot']) if payment.payment_method=='cash' else Decimal(1),'currency_config_version':p['currency_config_version']})

class QuoteRepository(SalesRepository):
    quotation_pricing_capable=True
    def __init__(self,db,plan):super().__init__(db,commit_on_save=False);self.plan=plan;self.products={};self.levels={};self.variants={}
    async def get_product(self,company,product):
        row=await super().get_product(company,product);self.products[str(product)]=row;return row
    async def get_variant(self,*args):
        row=await super().get_variant(*args);self.variants[str(args[2])]=row;return row
    async def get_price_level(self,*args):
        level=await super().get_price_level(*args)
        if level:
            level=(await self.db.execute(select(ProductPriceLevel).where(ProductPriceLevel.id==level.id).with_for_update(read=True).execution_options(populate_existing=True))).scalar_one_or_none()
            if not level or level.company_id!=args[0] or level.product_id!=args[1] or not level.active or level.deleted or level.name.lower()!=args[2].lower() or level.minimum_quantity>args[3]:raise HTTPException(409,'Customer tier changed during locked checkout')
        self.levels[(str(args[1]),Decimal(args[3]))]=level;return level
    def check(self,items):
        expected={(r['product_id'],r['variant_id']):r for r in self.plan['items']}
        if len(items)!=len(expected):raise HTTPException(409,'Accepted quotation positions differ')
        for item in items:
            r=expected[(str(item.product_id),str(item.variant_id) if item.variant_id else None)];p=self.products[str(item.product_id)]
            level=self.levels.get((str(item.product_id),Decimal(item.quantity)));variant=self.variants.get(str(item.variant_id)) if item.variant_id else None
            catalog_price=level.price if level else variant.selling_price if variant and variant.selling_price is not None else p.selling_price
            factor=1 if r['entered_unit'].strip().lower()==p.unit else p.units_per_purchase if r['entered_unit'].strip().lower()==str(p.purchase_unit or '').lower() else 0
            if (Decimal(catalog_price)!=Decimal(r['price']) or Decimal(factor)!=Decimal(r['factor']) or item.selling_unit!=r['base_unit'] or item.quantity!=Decimal(r['base_quantity']) or item.unit_price!=Decimal(r['price']) or item.line_total!=Decimal(r['net']) or Decimal(item.tax_rate_snapshot)!=Decimal(r['tax_rate']) or bool(item.tax_exempt_snapshot)!=r['tax_exempt'] or bool(item.cost_snapshot_available)!=(r['cost'] is not None) or r['cost'] is not None and Decimal(item.unit_cost)!=Decimal(r['cost'])):raise HTTPException(409,'Locked checkout differs from accepted quotation snapshots')
            name=item.product_name+(f' ({item.variant_name_snapshot})' if item.variant_name_snapshot else '')
            if 'track_inventory' in r and bool(p.track_inventory)!=r['track_inventory']:raise HTTPException(409,'Locked inventory policy differs from accepted quotation')
            if name!=r['name'] or 'price_level_name' in r and item.price_level_name_snapshot!=r['price_level_name']:raise HTTPException(409,'Locked catalogue labels differ from accepted quotation source')
            item.tax_amount=Decimal(r['tax'])
    def totals(self,items):self.check(items);return tuple(Decimal(self.plan[k]) for k in ('subtotal','tax','total'))
