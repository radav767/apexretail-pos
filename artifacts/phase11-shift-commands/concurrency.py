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
from app.shifts.schema import ShiftOpen,ShiftClose,CashMovementCreate,OfflineSaleResolutionCreate
from app.business_operations.tips import TipService
from app.business_operations.tip_schema import TipConfigInput,TipInput
from app.models import ShiftCommandReceipt,OfflineSaleResolution,CashierShift,PosSession,TipEntry,CashierShiftCashMovement,Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
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
  opaque='synthetic-shift-race-'+str(uuid4())
  db.add(PosSession(company_id=company,shop_id=shop,branch_id=branch,device_id=device,employee_id=employee,token_hash=hash_session_token(opaque),session_version=0,expires_at=datetime.now(timezone.utc)+timedelta(hours=12)))
  await db.commit()
 async def submit(kind,data,shift_id=None):
  async with factory() as db:
   actor=await resolve_auth_actor(token if kind=='resolution' else opaque,db)
   service=ShiftService(ShiftRepository(db))
   try:
    if kind=='open':result=await service.open(data,actor)
    elif kind=='cash':result=await service.create_cash_movement(shift_id,data,actor)
    elif kind=='close':result=await service.close(shift_id,data,actor)
    else:result=await service.resolve_offline_sale(data,actor)
    return 200,str(result['id'])
   except HTTPException as error:return error.status_code,None
 opening=ShiftOpen(idempotency_key=str(uuid4()),opening_balances=[{'currency_code':'USD','amount':20}])
 opened=await asyncio.wait_for(asyncio.gather(*(submit('open',opening) for _ in range(3))),20)
 assert all(status==200 for status,_ in opened) and len({identity for _,identity in opened})==1,opened
 shift_id=UUID(opened[0][1])
 async with factory() as db:
  actor=await resolve_auth_actor(opaque,db);view=await ShiftService(ShiftRepository(db)).current(actor)
  shift_token=view['offline_shift_token'];captured=datetime.now(timezone.utc)
 cash=CashMovementCreate(idempotency_key=str(uuid4()),movement_type='cash_in',currency_code='USD',amount=10,reason='Synthetic confirmed manual float')
 repeated=await asyncio.wait_for(asyncio.gather(*(submit('cash',cash,shift_id) for _ in range(3))),20)
 assert all(status==200 for status,_ in repeated) and len({identity for _,identity in repeated})==1,repeated
 second=cash.model_copy(update={'idempotency_key':str(uuid4())})
 conflicts=await asyncio.wait_for(asyncio.gather(submit('cash',second,shift_id),submit('cash',second.model_copy(update={'reason':'Changed reason'}),shift_id)),20)
 assert sorted(status for status,_ in conflicts)==[200,409],conflicts
 closing=ShiftClose(idempotency_key=str(uuid4()),counted_balances=[{'currency_code':'USD','amount':40}],confirmed=True)
 async with factory() as db:
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='expired';await db.commit()
 closed=await asyncio.wait_for(asyncio.gather(*(submit('close',closing,shift_id) for _ in range(3))),20)
 assert all(status==200 for status,_ in closed),closed
 assert (await submit('cash',cash,shift_id))[0]==200 and (await submit('open',ShiftOpen(idempotency_key=str(uuid4()))))[0]==402
 sale=SaleCreate(company_id=company,branch_id=branch,device_id=device,employee_id=employee,client_sale_id=uuid4(),shift_id=shift_id,offline_shift_token=shift_token,client_created_at=captured,amount_received=100,items=[SaleItemCreate(product_id=product_id,quantity=2)])
 resolution=OfflineSaleResolutionCreate(action='post_to_original_shift',reason='Synthetic reviewed original queue',idempotency_key=str(uuid4()),sale=sale)
 assert (await submit('resolution',resolution))[0]==402
 async with factory() as db:
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='active';sub.current_period_ends_at=datetime.now(timezone.utc)+timedelta(days=1);await db.commit()
 resolved=await asyncio.wait_for(asyncio.gather(*(submit('resolution',resolution) for _ in range(3))),20)
 assert all(status==200 for status,_ in resolved) and len({identity for _,identity in resolved})==1,resolved
 # Normal queued upload and explicit manager resolution share sale->shift
 # ordering. A closed-shift normal upload may conflict, never deadlock or post twice.
 raced_sale=sale.model_copy(update={'client_sale_id':uuid4()})
 raced_resolution=resolution.model_copy(update={'idempotency_key':str(uuid4()),'sale':raced_sale})
 async def normal_upload():
  async with factory() as db:
   actor=await resolve_auth_actor(opaque,db)
   try:return 200,str((await SalesService(SalesRepository(db)).create_sale(raced_sale,actor=actor)).id)
   except HTTPException as error:return error.status_code,None
 race=await asyncio.wait_for(asyncio.gather(submit('resolution',raced_resolution),normal_upload()),20)
 assert race[0][0]==200 and race[1][0] in {403,409},race
 async with factory() as db:
  counts={name:(await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one() for name,model in [('shifts',CashierShift),('cash',CashierShiftCashMovement),('resolutions',OfflineSaleResolution),('sales',Sale),('stock_movements',InventoryMovement),('command_receipts',ShiftCommandReceipt)]}
  assert counts=={'shifts':1,'cash':2,'resolutions':2,'sales':2,'stock_movements':2,'command_receipts':6},counts
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one();assert quantity==96
  shift=await db.get(CashierShift,shift_id);assert shift.net_sales_base==0
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='suspended';await db.commit()
 assert (await submit('resolution',resolution))[0]==200
 result={'synthetic_only':True,'three_equal_open_cash_close_resolution_requests_one_result_each':True,'cash_conflicting_payload_statuses':sorted(status for status,_ in conflicts),'closure_allowed_after_expiry':True,'new_open_and_post_denied_after_expiry':True,'committed_resolution_replay_after_suspension':True,'normal_upload_vs_manager_resolution_statuses':[status for status,_ in race],'counts':counts,'stock':str(quantity),'closed_shift_summary_preserved':True,'provider_or_drawer_hardware_actions':False}
 Path('/tmp/phase11-shift-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
