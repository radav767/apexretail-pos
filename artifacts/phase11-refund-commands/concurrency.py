import asyncio,os,json
from pathlib import Path
from uuid import UUID,uuid4
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate,SaleItemCreate,RefundCreate,RefundItemCreate
from datetime import datetime,timezone
from app.expenses.service import ExpenseService
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate,ExpenseCreate
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.models import RefundCommandReceipt,Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  registered=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic Replay Owner',owner_pin='1234',business_name='Synthetic Sale Race',business_type='Retail',country='Zimbabwe',phone='000000000',email=f'{uuid4()}@example.com',password='synthetic-replay-password',confirm_password='synthetic-replay-password',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,shop,branch,device,employee=[UUID(registered[k]['id']) for k in ('company','shop','branch','device','employee')]
  token=registered['token']
  product=Product(company_id=company,name='Synthetic race item',selling_price=12,stock_qty=100)
  customer=Customer(company_id=company,customer_code='SYNTHETIC',name='Synthetic credit customer',credit_enabled=True,unlimited_credit=False,credit_limit=100)
  db.add_all([product,customer]);await db.flush();product_id,customer_id=product.id,customer.id
  db.add(InventoryBalance(company_id=company,shop_id=shop,branch_id=branch,product_id=product_id,quantity=100,reorder_level=0));await db.commit()
 async with factory() as db:
  actor=await resolve_auth_actor(token,db)
  original=await SalesService(SalesRepository(db)).create_sale(SaleCreate(company_id=company,branch_id=branch,device_id=device,employee_id=employee,client_sale_id=uuid4(),amount_received=1000,items=[SaleItemCreate(product_id=product_id,quantity=10)]),actor=actor)
  original_id=original.id
  item_id=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==original.id))).scalar_one()
 def command(quantity=1):return RefundCreate(request_id=uuid4(),company_id=company,branch_id=branch,device_id=device,original_sale_id=original_id,reason='Synthetic confirmed partial return',items=[RefundItemCreate(sale_item_id=item_id,quantity=quantity)])
 async def submit(data):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,str((await SalesService(SalesRepository(db)).create_refund(data,actor=actor)).id)
   except HTTPException as error:return error.status_code,None
 same=command(2);results=await asyncio.wait_for(asyncio.gather(*(submit(same) for _ in range(3))),20)
 assert all(status==200 for status,_ in results) and len({identity for _,identity in results})==1,results
 other=command();conflict=await asyncio.wait_for(asyncio.gather(submit(other),submit(other.model_copy(update={'reason':'Changed reason'}))),20)
 assert sorted(status for status,_ in conflict)==[200,409],conflict
 separate=await asyncio.wait_for(asyncio.gather(submit(command()),submit(command())),20)
 assert all(status==200 for status,_ in separate),separate
 async with factory() as db:
  counts={name:(await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one() for name,model in [('sales',Sale),('movements',InventoryMovement),('refund_receipts',RefundCommandReceipt)]}
  assert counts=={'sales':5,'movements':5,'refund_receipts':4},counts
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one();assert quantity==95
  refunded=(await db.execute(select(func.sum(SaleItem.quantity)).join(Sale,Sale.id==SaleItem.sale_id).where(Sale.company_id==company,Sale.original_sale_id==original_id))).scalar_one();assert refunded==5
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='expired';await db.commit()
 assert (await submit(same))[0]==200 and (await submit(command()))[0]==402
 result={'synthetic_only':True,'three_equal_partial_refunds_one_result':True,'conflicting_payload_statuses':sorted(status for status,_ in conflict),'different_refund_keys_serialized_original_sale':True,'counts':counts,'stock':str(quantity),'refunded_quantity':str(refunded),'committed_refund_after_expiry':True,'new_refund_denied':True,'real_payment_provider_actions':False}
 Path('/tmp/phase11-refund-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
