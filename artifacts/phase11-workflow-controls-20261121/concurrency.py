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
from app.workflows.recovery import RecoveryService
from app.inventory.transfer_service import TransferService
from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.workflows.schema import SupplierInput,POInput,VersionCommand,ReceiveInput,SupplierReturnInput,CountInput,MeasureInput,ReviewInput,CancellationInput
from app.models import Product,InventoryBalance,InventoryMovement,WorkflowCommand,CompanySubscription,Branch
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
   try:return 200,await getattr(CountService(db,actor) if method in {'create_count','measure','submit','recount','approve_count'} else RecoveryService(db,actor) if method=='cancel_uncommitted' else ProcurementService(db,actor),method)(*args)
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
 async with factory() as db:
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='active'
  destination=Branch(company_id=company,shop_id=shop,name='Synthetic reverse transfer branch');db.add(destination);await db.flush();other_branch=destination.id
  p1=Product(company_id=company,name='Synthetic outbound A',selling_price=5,stock_qty=10);p2=Product(company_id=company,name='Synthetic outbound B',selling_price=5,stock_qty=10)
  db.add_all([p1,p2]);await db.flush();pa,pb=p1.id,p2.id
  db.add_all([InventoryBalance(company_id=company,branch_id=branch,shop_id=shop,product_id=pa,quantity=10,reorder_level=0),InventoryBalance(company_id=company,branch_id=other_branch,shop_id=shop,product_id=pb,quantity=10,reorder_level=0)]);await db.commit()
 async def transfer(product,source,destination):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   movements=await TransferService(TransferRepository(db)).transfer(TransferCreate(company_id=company,source_branch_id=source,destination_branch_id=destination,request_id=uuid4(),reference='SYN-OPPOSITE-'+str(uuid4()),items=[dict(product_id=product,quantity=1)]),actor=actor)
   return len(movements)
 transfers=await asyncio.wait_for(asyncio.gather(transfer(pa,branch,other_branch),transfer(pb,other_branch,branch)),30);assert transfers==[2,2],transfers
 # Real existing transaction services race durable count approval using
 # separate connections, with synthetic cash bookkeeping only.
 from app.models import CompanySetting,SaleItem
 from app.sales.service import SalesService
 from app.sales.repository import SalesRepository
 from app.sales.schema import SaleCreate,SaleItemCreate,RefundCreate,RefundItemCreate
 device=UUID(r['device']['id'])
 async with factory() as db:
  settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();settings.shift_enforcement_enabled=False;await db.commit()
 async def sale_or_refund(data):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);svc=SalesService(SalesRepository(db))
   sale=await (svc.create_refund(data,actor=actor) if isinstance(data,RefundCreate) else svc.create_sale(data,actor=actor))
   return 200,str(sale.id)
 async def reviewed_count(product):
  _,row=await execute('create_count',CountInput(company_id=company,request_id=uuid4(),branch_id=branch,scope='partial',product_ids=[product]))
  measured=[dict(key=e['key'],quantity=str(Decimal(e['baseline'])-1)) for e in row['payload']['rows']]
  _,row=await execute('measure',UUID(row['id']),MeasureInput(company_id=company,request_id=uuid4(),version=row['version'],measurements=measured))
  _,row=await execute('submit',UUID(row['id']),VersionCommand(company_id=company,request_id=uuid4(),version=row['version']))
  return row
 async def quantity_at(product,at=branch):
  async with factory() as db:return (await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==product,InventoryBalance.branch_id==at))).scalar_one()
 async def approve_racing(row,other):
  results=await asyncio.wait_for(asyncio.gather(execute('approve_count',UUID(row['id']),ReviewInput(company_id=company,request_id=uuid4(),version=row['version'],reason='Synthetic transaction race review')),other),30)
  assert results[0][0] in (200,409) and results[1][0]==200,results
  return results
 conflict_count=await reviewed_count(pa);conflict_before=await quantity_at(pa)
 conflict_approvals=await asyncio.wait_for(asyncio.gather(*[execute('approve_count',UUID(conflict_count['id']),ReviewInput(company_id=company,request_id=uuid4(),version=conflict_count['version'],reason='Synthetic concurrent approver')) for _ in range(2)]),30)
 assert sorted(c for c,_ in conflict_approvals)==[200,409],conflict_approvals
 assert await quantity_at(pa)==conflict_before-1
 row=await reviewed_count(pid);before=await quantity_at(pid)
 sale_command=SaleCreate(company_id=company,branch_id=branch,device_id=device,client_sale_id=uuid4(),amount_received=100,items=[SaleItemCreate(product_id=pid,quantity=1)])
 sale_race=await approve_racing(row,sale_or_refund(sale_command))
 assert await quantity_at(pid)==before-1-(1 if sale_race[0][0]==200 else 0)
 async with factory() as db:item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==UUID(sale_race[1][1])))).scalar_one()
 row=await reviewed_count(pid);before=await quantity_at(pid)
 refund_command=RefundCreate(company_id=company,branch_id=branch,device_id=device,request_id=uuid4(),original_sale_id=UUID(sale_race[1][1]),reason='Synthetic count race return',items=[RefundItemCreate(sale_item_id=item,quantity=1)])
 refund_race=await approve_racing(row,sale_or_refund(refund_command))
 assert await quantity_at(pid)==before+1-(1 if refund_race[0][0]==200 else 0)
 row=await reviewed_count(pa);before=await quantity_at(pa);destination_before=await quantity_at(pa,other_branch)
 async def transfer_status():return 200,await transfer(pa,branch,other_branch)
 transfer_race=await approve_racing(row,transfer_status())
 assert await quantity_at(pa)==before-1-(1 if transfer_race[0][0]==200 else 0)
 assert await quantity_at(pa,other_branch)==destination_before+1
 request=uuid4();original=SupplierInput(company_id=company,request_id=request,name='Synthetic cancellation race')
 cancel=CancellationInput(company_id=company,request_id=request,reason='Synthetic review fence',original_kind='supplier_create',original_payload=original.model_dump(mode='json'))
 cancelled=await asyncio.wait_for(asyncio.gather(execute('supplier',original),execute('cancel_uncommitted',cancel)),30)
 assert cancelled[1][0]==200,cancelled
 if cancelled[0][0]==200:assert cancelled[1][1]['status']=='committed'
 else:assert cancelled[0][0]==409 and cancelled[1][1]['status']=='cancelled'
 late=await execute('supplier',original);assert late[0]==cancelled[0][0]
 result={'synthetic_only':True,'equal_receipts_one_grn':True,'distinct_final_receipt_statuses':[c for c,_ in final],'equal_supplier_returns_one_movement':True,'return_budget_race_statuses':[c for c,_ in returns],'equal_count_approvals_one_movement':True,'count_vs_grn_statuses':[c for c,_ in race],'stock':str(quantity),'procurement_count_stage_movements':movements,'expired_exact_replay':True,'opposite_transfers_different_products_no_deadlock':True,'cancel_vs_original_statuses':[c for c,_ in cancelled],'cancel_outcome':cancelled[1][1]['status'],'late_packet_matches_durable_outcome':True,'count_vs_sale_statuses':[c for c,_ in sale_race],'count_vs_refund_statuses':[c for c,_ in refund_race],'count_vs_transfer_statuses':[c for c,_ in transfer_race],'different_count_approval_ids_statuses':[c for c,_ in conflict_approvals],'transaction_race_quantities_verified':True,'providers_messages_production':False}
 Path('/tmp/phase11-workflow-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
