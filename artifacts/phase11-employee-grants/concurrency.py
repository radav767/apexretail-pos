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
from datetime import timedelta
from app.auth.security import hash_session_token
from app.shifts.service import ShiftService
from app.shifts.repository import ShiftRepository
from app.shifts.schema import ShiftOpen
from app.business_operations.tips import TipService
from app.business_operations.tip_schema import TipConfigInput,TipInput
from app.employees.service import EmployeeService
from app.employees.repository import EmployeeRepository
from app.employees.admin_service import EmployeeAdminService
from app.employees.schema import EmployeeUpdate,PinLoginRequest,RoleCreate,RoleUpdate
from app.employees.logout import logout_context,LogoutContext
from app.subscriptions.offline_actor import grant_for
from app.models import Employee,Device,PosSession,TipEntry,CashierShiftCashMovement,Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
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
  opaque='synthetic-security-race-'+str(uuid4())
  register_key=(await db.get(Device,device)).device_key
  db.add(PosSession(company_id=company,shop_id=shop,branch_id=branch,device_id=device,employee_id=employee,token_hash=hash_session_token(opaque),session_version=0,expires_at=datetime.now(timezone.utc)+timedelta(hours=12)))
  await db.commit()
 reset_ready,logout_ready,start=asyncio.Event(),asyncio.Event(),asyncio.Event()
 async def reset():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);reset_ready.set();await start.wait()
   await EmployeeService(EmployeeRepository(db)).update(company,employee,EmployeeUpdate(pin='5678'),actor)
 async def logout():
  async with factory() as db:
   actor=await resolve_auth_actor(opaque,db);assert actor;logout_ready.set();await start.wait()
   await logout_context(db,actor,LogoutContext())
 tasks=[asyncio.create_task(reset()),asyncio.create_task(logout())]
 await asyncio.wait_for(asyncio.gather(reset_ready.wait(),logout_ready.wait()),10);start.set()
 await asyncio.wait_for(asyncio.gather(*tasks),20)
 async def pin():
  async with factory() as db:
   return (await EmployeeService(EmployeeRepository(db)).pin_login(PinLoginRequest(company_id=company,shop_id=shop,branch_id=branch,device_id=device,device_key=register_key,pin='5678')))['access_token']
 async with factory() as db:
  assert (await db.get(Employee,employee)).session_version==2
  assert await resolve_auth_actor(opaque,db) is None
 current=await pin()
 async with factory() as db:
  actor=await resolve_auth_actor(current,db);grant=await grant_for(db,actor);assert grant['actions']['sale'] and grant['session_version']==2
  await db.commit()
 async with factory() as db:
  actor=await resolve_auth_actor(token,db)
  role=await EmployeeAdminService(db).create_role(RoleCreate(company_id=company,name='Synthetic bounded grants',permissions={'sales_process':True}),actor)
  role_id=role['id']
  await EmployeeService(EmployeeRepository(db)).update(company,employee,EmployeeUpdate(role_id=role_id),actor)
  assert (await db.get(Employee,employee)).session_version==3
 current=await pin()
 grant_ready,role_ready,start=asyncio.Event(),asyncio.Event(),asyncio.Event()
 async def issue_grant():
  async with factory() as db:
   actor=await resolve_auth_actor(current,db);assert actor;grant_ready.set();await start.wait()
   try:
    grant=await grant_for(db,actor);assert grant['session_version']==3 and grant['actions']['sale']
    await db.commit();return 200
   except HTTPException as error:assert error.status_code==401;return 401
 async def reduce_role():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);role_ready.set();await start.wait()
   await EmployeeAdminService(db).update_role(company,role_id,RoleUpdate(permissions={'sales_process':False}),actor)
 tasks=[asyncio.create_task(issue_grant()),asyncio.create_task(reduce_role())]
 await asyncio.wait_for(asyncio.gather(grant_ready.wait(),role_ready.wait()),10);start.set()
 race=await asyncio.wait_for(asyncio.gather(*tasks),20)
 async with factory() as db:
  assert (await db.get(Employee,employee)).session_version==4
  assert await resolve_auth_actor(current,db) is None
 fresh=await pin()
 async with factory() as db:
  actor=await resolve_auth_actor(fresh,db);grant=await grant_for(db,actor)
  assert grant['session_version']==4 and not grant['actions']['sale']
 result={'synthetic_only':True,'pin_reset_and_logout_atomic_epoch':2,'prior_opaque_revoked':True,'fresh_pin_uses_current_epoch':True,'grant_vs_role_revocation_status':race[0],'role_revocation_final_epoch':4,'stale_role_credential_cannot_renew':True,'fresh_current_grant_denies_withdrawn_sale_right':True,'no_lock_inversion':True,'production_credentials_or_provider_actions':False}
 Path('/tmp/phase11-employee-grants-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
