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
from app.auth.security import create_employee_access_token
from app.employees.logout import logout_context,LogoutContext
from app.employees.repository import EmployeeRepository
from app.employees.service import EmployeeService
from app.employees.schema import PinLoginRequest
from app.models import Employee,PosSession,Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
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
 async with factory() as db:
  emp=await db.get(Employee,employee)
  legacy=create_employee_access_token(employee_id=str(employee),company_id=str(company),role=emp.role)
  register_key=(await db.execute(select(__import__('app.models',fromlist=['Device']).Device.device_key).where(__import__('app.models',fromlist=['Device']).Device.id==device))).scalar_one()
 captured=asyncio.Event();resume=asyncio.Event()
 async def delayed_pin():
  async with factory() as db:
   repo=EmployeeRepository(db);original=repo.active_pin_candidates
   async def candidates(*args):
    result=await original(*args);captured.set();await resume.wait();return result
   repo.active_pin_candidates=candidates
   return await EmployeeService(repo).pin_login(PinLoginRequest(company_id=company,branch_id=branch,shop_id=shop,device_id=device,device_key=register_key,pin='1234'))
 task=asyncio.create_task(delayed_pin());await asyncio.wait_for(captured.wait(),10)
 async with factory() as db:
  actor=await resolve_auth_actor(legacy,db);assert actor
  await logout_context(db,actor,LogoutContext())
 resume.set();late=await asyncio.wait_for(task,20)
 async with factory() as db:
  assert await resolve_auth_actor(late['access_token'],db) is None
  try:actor=await resolve_auth_actor(legacy,db)
  except HTTPException as error:assert error.status_code==401
  else:assert actor is None
  fresh=await EmployeeService(EmployeeRepository(db)).pin_login(PinLoginRequest(company_id=company,branch_id=branch,shop_id=shop,device_id=device,device_key=register_key,pin='1234',session_token=late['access_token']))
  actor=await resolve_auth_actor(fresh['access_token'],db);assert actor and actor.employee.session_version==1
 # Concurrent revocations with already-authenticated contexts must increment,
 # never overwrite the other request's epoch or expose a reusable owner token.
 async def revoke_ready(ready,start):
  async with factory() as db:
   actor=await resolve_auth_actor(fresh['access_token'],db);assert actor
   ready.set();await start.wait();return await logout_context(db,actor,LogoutContext())
 first,second,start=asyncio.Event(),asyncio.Event(),asyncio.Event()
 tasks=[asyncio.create_task(revoke_ready(first,start)),asyncio.create_task(revoke_ready(second,start))]
 await asyncio.wait_for(asyncio.gather(first.wait(),second.wait()),10);start.set();await asyncio.wait_for(asyncio.gather(*tasks),20)
 async with factory() as db:
  assert (await db.get(Employee,employee)).session_version==3
  assert await resolve_auth_actor(fresh['access_token'],db) is None
 result={'synthetic_only':True,'pin_read_before_logout_cannot_resurrect':True,'fresh_pin_after_logout_works':True,'concurrent_revocations_atomic_final_epoch':3,'previous_opaque_and_jwt_invalid':True,'real_provider_actions':False}
 Path('/tmp/phase11-pos-logout-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
