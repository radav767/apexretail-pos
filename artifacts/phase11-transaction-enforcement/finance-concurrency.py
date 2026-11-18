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
from app.sales.schema import SaleCreate,SaleItemCreate
from datetime import datetime,timezone
from app.expenses.service import ExpenseService
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate,ExpenseCreate
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.models import Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
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
  category=await ExpenseService(ExpenseRepository(db)).create_category(ExpenseCategoryCreate(company_id=company,name='Synthetic supplies'),actor)
  category_id=category.id
  sale=await SalesService(SalesRepository(db)).create_sale(SaleCreate(company_id=company,branch_id=branch,device_id=device,employee_id=employee,client_sale_id=uuid4(),items=[SaleItemCreate(product_id=product_id,quantity=2)],payment_method='credit',customer_id=customer_id),actor=actor)
  receivable=(await db.execute(select(CreditReceivable).where(CreditReceivable.sale_id==sale.id))).scalar_one();receivable_id=receivable.id
 def expense():return ExpenseCreate(company_id=company,branch_id=branch,category_id=category_id,amount=10,payment_method='cash',description='Synthetic expense',occurred_at=datetime.now(timezone.utc),idempotency_key=str(uuid4()))
 def payment():return SettlementCreate(company_id=company,branch_id=branch,receivable_id=receivable_id,amount=5,payment_method='cash',idempotency_key=str(uuid4()))
 async def submit(kind,data):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:
    result=await (ExpenseService(ExpenseRepository(db)).create_expense(data,actor) if kind=='expense' else CreditService(CreditRepository(db)).create_settlement(data,actor))
    return 200,str(result.id if kind=='expense' else result['id'])
   except HTTPException as error:return error.status_code,None
 same_e,same_c=expense(),payment()
 for kind,data in [('expense',same_e),('collection',same_c)]:
  result=await asyncio.wait_for(asyncio.gather(*(submit(kind,data) for _ in range(3))),20)
  assert all(s==200 for s,_ in result) and len({identity for _,identity in result})==1
 conflicts={}
 for kind,data,field in [('expense',expense(),'description'),('collection',payment(),'note')]:
  result=await asyncio.wait_for(asyncio.gather(submit(kind,data),submit(kind,data.model_copy(update={field:'different'}))),20)
  conflicts[kind]=sorted(s for s,_ in result);assert conflicts[kind]==[200,409]
 # Different keys against one receivable must also serialize its balance.
 result=await asyncio.wait_for(asyncio.gather(submit('collection',payment()),submit('collection',payment())),20)
 assert all(s==200 for s,_ in result)
 async with factory() as db:
  counts={name:(await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one() for name,model in [('expenses',Expense),('collections',CreditSettlement),('sales',Sale),('movements',InventoryMovement)]}
  assert counts=={'expenses':2,'collections':4,'sales':1,'movements':1},counts
  outstanding=(await db.get(CreditReceivable,receivable_id)).outstanding_balance;assert outstanding==4,outstanding
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one();assert quantity==98
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='suspended';await db.commit()
 for kind,data,new in [('expense',same_e,expense()),('collection',same_c,payment())]:
  assert (await submit(kind,data))[0]==200 and (await submit(kind,new))[0]==402
 result={'synthetic_only':True,'equal_expense_and_collection_retries_one_result':True,'conflicting_payload_statuses':conflicts,'different_collection_keys_serialized_balance':True,'counts':counts,'outstanding':str(outstanding),'stock':str(quantity),'committed_replay_after_suspension':True,'new_writes_denied':True,'provider_actions':False}
 Path('/tmp/phase11-finance-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
