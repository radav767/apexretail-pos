import asyncio,os,json
from pathlib import Path
from uuid import UUID,uuid4
from datetime import datetime,timedelta,timezone
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
from app.auth.security import hash_session_token
from app.models import Product,InventoryBalance,Device,Employee,PosSession,PrinterStation,PrinterRoute,CompanySubscription,CommerceOrder,Sale,InventoryMovement,PrintJob
from app.models.business_operations import OrderSyncReceipt
from app.employees.permissions import normalize_permissions
from app.business_operations.service import BusinessService
from app.business_operations.offline import OfflineOrderService
from app.business_operations.schema import OrderInput,OrderItemInput,SettlementInput,OfflineDraftInput
from app.sales.schema import SaleCreate
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  registered=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic Operations Owner',owner_pin='1234',business_name='Synthetic Operation Race',business_type='Restaurant',country='Zimbabwe',phone='000000000',email=f'{uuid4()}@example.com',password='synthetic-operation-password',confirm_password='synthetic-operation-password',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,shop,branch,device,employee=[UUID(registered[k]['id']) for k in ('company','shop','branch','device','employee')];owner_token=registered['token']
  product=Product(company_id=company,name='Synthetic operation item',selling_price=12,stock_qty=100)
  other_device=Device(company_id=company,shop_id=shop,branch_id=branch,name='Second synthetic register',device_key=str(uuid4()))
  db.add_all([product,other_device]);await db.flush();product_id=product.id;second_device=other_device.id
  worker=await db.get(Employee,employee);worker.role='waiter';worker.permissions=normalize_permissions('waiter',{})
  secret='synthetic-operation-register-'+str(uuid4())
  db.add(PosSession(company_id=company,shop_id=shop,branch_id=branch,device_id=device,employee_id=employee,token_hash=hash_session_token(secret),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
  db.add(InventoryBalance(company_id=company,shop_id=shop,branch_id=branch,product_id=product_id,quantity=100,reorder_level=0))
  station=PrinterStation(company_id=company,shop_id=shop,branch_id=branch,device_id=device,name='Synthetic kitchen queue',purpose='kitchen',transport='system',address='',paper_width='80mm',auto_print=False,active=True)
  db.add(station);await db.flush();db.add(PrinterRoute(station_id=station.id,target_type='product',target_id=product_id));await db.commit()
 async def perform(action,token=owner_token):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await action(db,actor)
   except HTTPException as error:return error.status_code,None
 create=OrderInput(branch_id=branch,device_id=device,waiter_id=employee,request_id=uuid4())
 same=await asyncio.wait_for(asyncio.gather(*(perform(lambda db,actor:BusinessService(db,actor).create_order(create)) for _ in range(2))),20)
 assert [s for s,_ in same]==[200,200] and same[0][1]['id']==same[1][1]['id']
 conflict_data=create.model_copy(update={'request_id':uuid4()})
 conflict=await asyncio.wait_for(asyncio.gather(perform(lambda db,actor:BusinessService(db,actor).create_order(conflict_data)),perform(lambda db,actor:BusinessService(db,actor).create_order(conflict_data.model_copy(update={'device_id':second_device})))),20)
 assert sorted(s for s,_ in conflict)==[200,409]
 offline=OfflineDraftInput(request_id=uuid4(),employee_id=employee,captured_at=datetime.now(timezone.utc),order=OrderInput(branch_id=branch,device_id=device,request_id=uuid4()),items=[OrderItemInput(version=1,product_id=product_id,quantity=2)])
 offline_result=await asyncio.wait_for(asyncio.gather(*(perform(lambda db,actor:OfflineOrderService(db,actor).synchronize(offline),secret) for _ in range(2))),20)
 assert [s for s,_ in offline_result]==[200,200] and sorted(result['already_synchronized'] for _,result in offline_result)==[False,True]
 async with factory() as db:
  actor=await resolve_auth_actor(owner_token,db);svc=BusinessService(db,actor);order=same[0][1]
  order=await svc.add_item(order['id'],OrderItemInput(version=order['version'],product_id=product_id,quantity=2));order=(await svc.send_kitchen(order['id'],order['version']))['order']
  payment=SettlementInput(version=order['version'],payment=SaleCreate(company_id=company,items=[],amount_received=100))
 settle=await asyncio.wait_for(asyncio.gather(*(perform(lambda db,actor:BusinessService(db,actor).settle(order['id'],payment)) for _ in range(2))),20)
 assert [s for s,_ in settle]==[200,200] and settle[0][1]['sale_id']==settle[1][1]['sale_id']
 async with factory() as db:
  counts={name:(await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one() for name,model in [('orders',CommerceOrder),('sales',Sale),('movements',InventoryMovement),('sync_receipts',OrderSyncReceipt),('print_jobs',PrintJob)]}
  stock=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one()
  assert counts=={'orders':3,'sales':1,'movements':1,'sync_receipts':1,'print_jobs':1} and stock==98
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='expired';sub.commercial_terms={'features':{}};await db.commit()
 assert (await perform(lambda db,actor:BusinessService(db,actor).create_order(create)))[0]==200
 assert (await perform(lambda db,actor:BusinessService(db,actor).settle(order['id'],payment)))[0]==200
 assert (await perform(lambda db,actor:OfflineOrderService(db,actor).synchronize(offline),secret))[0]==200
 pending=offline.model_copy(update={'request_id':uuid4(),'order':offline.order.model_copy(update={'request_id':uuid4()})})
 assert (await perform(lambda db,actor:OfflineOrderService(db,actor).synchronize(pending),secret))[0]==402
 result={'synthetic_only':True,'same_create_one_order':True,'different_register_same_identity_statuses':sorted(s for s,_ in conflict),'duplicate_offline_one_ack':True,'duplicate_settlement_one_sale':True,'counts':counts,'stock':str(stock),'committed_replays_after_expiry_and_module_removal':True,'new_offline_mutation_denied':True,'physical_printing_or_provider_action':False}
 Path('/tmp/phase11-operation-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
