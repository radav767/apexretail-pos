"""Independent read-only checks of final synthetic shell tenants only."""
import asyncio,os,json
from pathlib import Path
from uuid import UUID
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import (Sale,SaleCommandReceipt,RefundCommandReceipt,QuotationCommand,CommerceOrder,VariantInventoryBalance,ProductVariant,InventoryBalance,CashierShift,CashierShiftCurrencySnapshot)
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False);evidence={}
 async with factory() as db:
  bounded=json.loads(Path('/tmp/phase11-quotation-bounded-shell-result.json').read_text());assert bounded['synthetic_only'];company=UUID(bounded['company']);product=UUID(bounded['product'])
  async def count(model,c):return (await db.execute(select(func.count()).select_from(model).where(model.company_id==c))).scalar_one()
  rows=(await db.execute(select(Sale).where(Sale.company_id==company))).scalars().all();originals=[r for r in rows if not r.original_sale_id];refunds=[r for r in rows if r.original_sale_id];assert len(originals)==10 and len(refunds)==10;assert sum(r.total_amount for r in rows)==Decimal('608.70');assert await count(SaleCommandReceipt,company)==10 and await count(RefundCommandReceipt,company)==10 and await count(QuotationCommand,company)==30
  variants=dict((await db.execute(select(ProductVariant.name,VariantInventoryBalance.quantity).join(VariantInventoryBalance,VariantInventoryBalance.variant_id==ProductVariant.id).where(ProductVariant.company_id==company,ProductVariant.product_id==product))).all());assert variants=={'Red':570,'Blue':385},variants
  shift=(await db.execute(select(CashierShift).where(CashierShift.company_id==company))).scalar_one();assert shift.status=='closed' and shift.net_sales_base==0
  currencies=(await db.execute(select(CashierShiftCurrencySnapshot).where(CashierShiftCurrencySnapshot.shift_id==shift.id))).scalars().all();assert all(c.variance==0 for c in currencies);assert all(c.expected_cash==(20 if c.currency_code=='USD' else 0) for c in currencies)
  evidence['bounded']={'company':str(company),'originals':10,'refunds':10,'sale_proofs':10,'refund_proofs':10,'quotation_commands':30,'net_base_revenue':'608.70','variant_stock':{k:str(v) for k,v in variants.items()},'closed_shift_net_base':'0','all_variances':'0','frozen_precisions':[c.decimal_places_snapshot for c in currencies if c.currency_code!='USD']}
  recovery=json.loads(Path('/tmp/phase11-quotation-recovery-shell-result.json').read_text());assert recovery['synthetic_only'];company=UUID(recovery['company']);product=UUID(recovery['product'])
  assert await count(SaleCommandReceipt,company)==2 and await count(RefundCommandReceipt,company)==2 and await count(CommerceOrder,company)==319 and await count(QuotationCommand,company)==11
  balance=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company,InventoryBalance.product_id==product))).scalar_one();assert balance==94
  evidence['recovery']={'company':str(company),'orders':319,'quotation_commands':11,'sale_proofs':2,'refund_proofs':2,'stock':'94','held_old_actor_save_was_committed_without_stock':True}
 Path('/tmp/phase11-quotation-acceptance-persistence.json').write_text(json.dumps({'synthetic_only':True,'independent_read_only':True,**evidence},indent=2)+'\n');print(json.dumps(evidence));await engine.dispose()
asyncio.run(main())
