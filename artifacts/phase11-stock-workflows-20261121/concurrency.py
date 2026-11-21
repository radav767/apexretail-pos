import asyncio,os,json
from pathlib import Path
from uuid import uuid4,UUID
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.workflows.procurement import ProcurementService
from app.workflows.counts import CountService
from app.workflows.schema import SupplierInput,POInput,VersionCommand,ReceiveInput,SupplierReturnInput,CountInput,MeasureInput,ReviewInput
from app.models import Product,InventoryBalance,InventoryMovement,WorkflowCommand,CompanySubscription
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  r=await AuthService(AuthRepository(db)).register(RegisterRequest(business_name='Synthetic procurement race',email=f'{uuid4()}@example.com',password='Synthetic-Catalog-Only-123!',confirm_password='Synthetic-Catalog-Only-123!',owner_name='Synthetic Owner',owner_pin='1234',business_type='Retail',country='Zimbabwe',phone='000000000',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,branch,shop=[UUID(r[k]['id']) for k in ('company','branch','shop')];token=r['token']
  product=Product(company_id=company,name='Synthetic procurement stock',selling_price=12,cost_price=2,stock_qty=100);db.add(product);await db.flush();pid=product.id
  db.add(InventoryBalance(company_id=company,branch_id=branch,shop_id=shop,product_id=pid,quantity=100,reorder_level=0));await db.commit()
 async def execute(method,*args):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await getattr(CountService(db,actor) if method in {'create_count','measure','submit','recount','approve_count'} else ProcurementService(db,actor),method)(*args)
   except HTTPException as error:return error.status_code,None
 _,supplier=await execute('supplier',SupplierInput(company_id=company,request_id=uuid4(),name='Synthetic supplier'))
 line=uuid4();_,po=await execute('create_po',POInput(company_id=company,request_id=uuid4(),branch_id=branch,supplier_id=UUID(supplier['id']),lines=[dict(line_id=line,product_id=pid,quantity=10,unit='each',unit_cost=3)]))
 oid=UUID(po['id']);_,po=await execute('approve',oid,VersionCommand(company_id=company,request_id=uuid4(),version=po['version']))
 receipt=ReceiveInput(company_id=company,request_id=uuid4(),version=po['version'],reference='SYN-RACE',lines=[dict(line_id=line,quantity=4)])
 same=await asyncio.wait_for(asyncio.gather(*[execute('receive',oid,receipt) for _ in range(3)]),30);assert all(c==200 for c,_ in same),same
 po=same[0][1]['order'];ids=[result['lines'][0]['movement_id'] for _,result in same];assert len(set(ids))==1
 a=ReceiveInput(company_id=company,request_id=uuid4(),version=po['version'],reference='SYN-FINAL-A',lines=[dict(line_id=line,quantity=6)])
 b=a.model_copy(update={'request_id':uuid4(),'reference':'SYN-FINAL-B'})
 final=await asyncio.wait_for(asyncio.gather(execute('receive',oid,a),execute('receive',oid,b)),30);assert sorted(c for c,_ in final)==[200,409],final
 returned=SupplierReturnInput(company_id=company,request_id=uuid4(),receipt_id=receipt.request_id,line_id=line,quantity=1,reason='Synthetic supplier return')
 equal=await asyncio.wait_for(asyncio.gather(*[execute('supplier_return',oid,returned) for _ in range(3)]),30);assert all(c==200 for c,_ in equal) and len({r['movement_id'] for _,r in equal})==1,equal
 a=returned.model_copy(update={'request_id':uuid4(),'quantity':Decimal('3')});b=a.model_copy(update={'request_id':uuid4()})
 returns=await asyncio.wait_for(asyncio.gather(execute('supplier_return',oid,a),execute('supplier_return',oid,b)),30);assert sorted(c for c,_ in returns)==[200,409],returns
 _,count=await execute('create_count',CountInput(company_id=company,request_id=uuid4(),branch_id=branch,scope='partial',product_ids=[pid]))
 measured=[dict(key=row['key'],quantity='105') for row in count['payload']['rows']]
 _,count=await execute('measure',UUID(count['id']),MeasureInput(company_id=company,request_id=uuid4(),version=count['version'],measurements=measured))
 _,count=await execute('submit',UUID(count['id']),VersionCommand(company_id=company,request_id=uuid4(),version=count['version']))
 approval=ReviewInput(company_id=company,request_id=uuid4(),version=count['version'],reason='Synthetic variance reviewed')
 count_equal=await asyncio.wait_for(asyncio.gather(*[execute('approve_count',UUID(count['id']),approval) for _ in range(3)]),30)
 assert all(c==200 for c,_ in count_equal) and len({r['movement_ids'][0] for _,r in count_equal})==1,count_equal
 # A later count racing an independently approved GRN either precedes the
 # receipt or detects the movement cutoff. Both outcomes preserve stock.
 _,po2=await execute('create_po',POInput(company_id=company,request_id=uuid4(),branch_id=branch,supplier_id=UUID(supplier['id']),lines=[dict(line_id=line,product_id=pid,quantity=1,unit='each',unit_cost=3)]))
 _,po2=await execute('approve',UUID(po2['id']),VersionCommand(company_id=company,request_id=uuid4(),version=po2['version']))
 _,next_count=await execute('create_count',CountInput(company_id=company,request_id=uuid4(),branch_id=branch,scope='partial',product_ids=[pid]))
 _,next_count=await execute('measure',UUID(next_count['id']),MeasureInput(company_id=company,request_id=uuid4(),version=next_count['version'],measurements=[dict(key=next_count['payload']['rows'][0]['key'],quantity='104')]))
 _,next_count=await execute('submit',UUID(next_count['id']),VersionCommand(company_id=company,request_id=uuid4(),version=next_count['version']))
 race=await asyncio.wait_for(asyncio.gather(execute('approve_count',UUID(next_count['id']),ReviewInput(company_id=company,request_id=uuid4(),version=next_count['version'],reason='Cutoff race reviewed')),execute('receive',UUID(po2['id']),ReceiveInput(company_id=company,request_id=uuid4(),version=po2['version'],reference='SYN-CUTOFF',lines=[dict(line_id=line,quantity=1)]))),30)
 assert race[1][0]==200 and race[0][0] in (200,409),race
 async with factory() as db:
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one();assert quantity==(105 if race[0][0]==200 else 106)
  movements=(await db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one();assert movements==(7 if race[0][0]==200 else 6)
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='expired';await db.commit()
 assert (await execute('receive',oid,receipt))[0]==200
 result={'synthetic_only':True,'equal_receipts_one_grn':True,'distinct_final_receipt_statuses':[c for c,_ in final],'equal_supplier_returns_one_movement':True,'return_budget_race_statuses':[c for c,_ in returns],'equal_count_approvals_one_movement':True,'count_vs_grn_statuses':[c for c,_ in race],'stock':str(quantity),'movements':movements,'expired_exact_replay':True,'providers_messages_production':False}
 Path('/tmp/phase11-workflow-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
