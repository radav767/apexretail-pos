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
from app.models import PosSession,TipEntry,CashierShiftCashMovement,Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
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
  sale=await SalesService(SalesRepository(db)).create_sale(SaleCreate(company_id=company,branch_id=branch,device_id=device,employee_id=employee,client_sale_id=uuid4(),amount_received=100,items=[SaleItemCreate(product_id=product_id,quantity=2)]),actor=actor)
  sale_id=sale.id
  await TipService(db,actor).configure(TipConfigInput(enabled=True,policy='staff'))
  opaque='synthetic-tip-race-'+str(uuid4())
  db.add(PosSession(company_id=company,shop_id=shop,branch_id=branch,device_id=device,employee_id=employee,token_hash=hash_session_token(opaque),session_version=0,expires_at=datetime.now(timezone.utc)+timedelta(hours=12)))
  await db.commit();cashier=await resolve_auth_actor(opaque,db)
  shift=await ShiftService(ShiftRepository(db)).open(ShiftOpen(idempotency_key=str(uuid4())),cashier)
 command=TipInput(request_id=uuid4(),shift_id=shift['id'],kind='collect',sale_id=sale_id,payment_method='cash',currency_code='USD',amount=10,reason='Synthetic confirmed manual transfer',confirmed=True)
 async def submit(data):
  async with factory() as db:
   actor=await resolve_auth_actor(opaque,db)
   try:return 200,str((await TipService(db,actor).record(data))['id'])
   except HTTPException as error:return error.status_code,None
 same=await asyncio.wait_for(asyncio.gather(*(submit(command) for _ in range(3))),20)
 assert all(status==200 for status,_ in same) and len({value for _,value in same})==1,same
 next_command=command.model_copy(update={'request_id':uuid4()})
 conflict=await asyncio.wait_for(asyncio.gather(submit(next_command),submit(next_command.model_copy(update={'reason':'Different reason'}))),20)
 assert sorted(status for status,_ in conflict)==[200,409]
 async with factory() as db:
  counts={name:(await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one() for name,model in [('tips',TipEntry),('cash_movements',CashierShiftCashMovement),('sales',Sale),('stock_movements',InventoryMovement)]}
  assert counts=={'tips':2,'cash_movements':2,'sales':1,'stock_movements':1},counts
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one();assert quantity==98
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='suspended';await db.commit()
 assert (await submit(command))[0]==200 and (await submit(command.model_copy(update={'request_id':uuid4()})))[0]==402
 result={'synthetic_only':True,'manual_test_transfer_ledger_only':True,'three_equal_tip_requests_one_receipt':True,'conflicting_payload_statuses':sorted(status for status,_ in conflict),'counts':counts,'stock':str(quantity),'committed_replay_after_suspension':True,'new_tip_denied':True,'provider_or_cash_drawer_hardware_actions':False}
 Path('/tmp/phase11-tip-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
