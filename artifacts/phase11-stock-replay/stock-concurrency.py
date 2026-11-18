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
from datetime import date,timedelta
from app.inventory.service import InventoryService
from app.inventory.repository import InventoryRepository
from app.inventory.schema import StockTakeCreate
from app.inventory.transfer_service import TransferService
from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.business_operations.batch_stock import BatchStockService
from app.business_operations.schema import BatchStockInput,ProfileInput
from app.business_operations.service import BusinessService
from app.models import Branch,Expense,CreditSettlement,Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
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
  destination=Branch(company_id=company,shop_id=shop,name='Synthetic race destination');db.add(destination);await db.commit();destination_id=destination.id
  await BusinessService(db,actor).save_profile(ProfileInput(profile='pharmacy'))
 count=StockTakeCreate(company_id=company,branch_id=branch,request_id=uuid4(),items=[{'product_id':product_id,'expected_qty':100,'physical_qty':90}])
 transfer=TransferCreate(company_id=company,source_branch_id=branch,destination_branch_id=destination_id,request_id=uuid4(),items=[{'product_id':product_id,'quantity':5}])
 batch=BatchStockInput(request_id=uuid4(),branch_id=branch,product_id=product_id,code='SYNTHETIC-RACE',expires_on=date.today()+timedelta(days=30),operation='receive',quantity=2,reason='Synthetic confirmed stock')
 async def submit(kind,data):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:
    if kind=='count':result=await InventoryService(InventoryRepository(db)).stock_take(data,actor=actor)
    elif kind=='transfer':result=await TransferService(TransferRepository(db)).transfer(data,actor=actor)
    else:result=await BatchStockService(db,actor).execute(data)
    return 200,([str(row.id) for row in result] if isinstance(result,list) else str(result['movement_id']))
   except HTTPException as error:return error.status_code,None
 for kind,data in [('count',count),('transfer',transfer),('batch',batch)]:
  results=await asyncio.wait_for(asyncio.gather(*(submit(kind,data) for _ in range(3))),20)
  assert all(status==200 for status,_ in results) and all(result==results[0][1] for _,result in results),results
 changed=batch.model_copy(update={'request_id':uuid4(),'quantity':Decimal(3)})
 conflict=await asyncio.wait_for(asyncio.gather(submit('batch',changed),submit('batch',changed.model_copy(update={'quantity':Decimal(4)}))),20)
 assert sorted(status for status,_ in conflict)==[200,409]
 async with factory() as db:
  movements=(await db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one();assert movements==5,movements
  rows=(await db.execute(select(InventoryBalance).where(InventoryBalance.company_id==company))).scalars().all()
  quantities={row.branch_id:row.quantity for row in rows};assert quantities[branch] in {Decimal(90),Decimal(91)} and quantities[destination_id]==5
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='expired';sub.commercial_terms={'features':{}};await db.commit()
 for kind,data in [('count',count),('transfer',transfer),('batch',batch)]:
  assert (await submit(kind,data))[0]==200
  assert (await submit(kind,data.model_copy(update={'request_id':uuid4()})))[0]==402
 result={'synthetic_only':True,'three_equal_count_transfer_batch_retries_one_result_each':True,'conflicting_batch_payload_statuses':sorted(status for status,_ in conflict),'movements':movements,'source_stock':str(quantities[branch]),'destination_stock':str(quantities[destination_id]),'committed_replay_after_expiry_and_module_removal':True,'new_stock_commands_denied':True,'real_provider_actions':False}
 Path('/tmp/phase11-stock-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
