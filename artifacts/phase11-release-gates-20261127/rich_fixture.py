"""Synthetic production-era preservation corpus, private socket only; never prod."""
import argparse,hashlib,json,sys
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timezone,timedelta,date
from decimal import Decimal
import sqlalchemy as sa
P=argparse.ArgumentParser();P.add_argument('action',choices=['seed','controls']);P.add_argument('--database',choices=['apex_phase11_release_rich_upgrade','apex_phase11_release_rich_qualification'],default='apex_phase11_release_rich_upgrade');args=P.parse_args()
ROOT=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');DB=args.database;SOCKET='/tmp/apex-phase11-release-pg-ysjagwtm';PORT='55443'
e=sa.create_engine(sa.URL.create('postgresql+psycopg2',username='postgres',database=DB,query={'host':SOCKET,'port':PORT}));m=sa.MetaData();m.reflect(e);now=datetime.now(timezone.utc)
def put(c,table,**v):
 t=m.tables[table]
 for col in t.columns:
  if col.name in v or col.nullable or col.server_default is not None:continue
  if col.foreign_keys:raise AssertionError('Explicit foreign key required: '+table+'.'+col.name)
  if isinstance(col.type,sa.UUID):v[col.name]=uuid4()
  elif isinstance(col.type,sa.DateTime):v[col.name]=now
  elif isinstance(col.type,sa.Date):v[col.name]=date.today()
  elif isinstance(col.type,sa.Boolean):v[col.name]=col.name=='active'
  elif isinstance(col.type,(sa.Numeric,sa.Integer)):v[col.name]=0
  elif isinstance(col.type,sa.JSON):v[col.name]={}
  elif isinstance(col.type,sa.String):v[col.name]='synthetic'
  else:raise AssertionError('Explicit value required: '+table+'.'+col.name)
 c.execute(t.insert().values(**v));return v.get('id')
def h(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
if args.action=='seed':
 with e.begin() as c:
  assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()=='p10a_platform_management'
  assert c.exec_driver_sql('SELECT count(*) FROM companies').scalar_one()==0
  co=put(c,'companies',name='Synthetic rich release',owner_email='rich@example.invalid',business_type='Retail')
  user=put(c,'users',company_id=co,email='rich@example.invalid',password_hash='not-login-capable',role='owner')
  foreign=put(c,'companies',name='Synthetic isolated foreign',owner_email='foreign-rich@example.invalid',business_type='Retail')
  shop=put(c,'shops',company_id=co,name='Rich shop');branch=put(c,'branches',company_id=co,shop_id=shop,name='Rich branch')
  context=dict(company_id=co,shop_id=shop,branch_id=branch)
  device=put(c,'devices',**context,name='Retained register',device_key=str(uuid4()),status='active',platform='web',assignment_revision=1)
  employee=put(c,'employees',**context,name='Rich cashier',pin='not-login-capable',role='cashier',permissions={'sales':True},role_overrides={})
  session=put(c,'pos_sessions',**context,employee_id=employee,device_id=device,token_hash=h('valid synthetic token'),expires_at=now+timedelta(days=1))
  revoked=put(c,'pos_sessions',**context,employee_id=employee,device_id=device,token_hash=h('revoked synthetic token'),expires_at=now+timedelta(days=1),revoked_at=now-timedelta(minutes=1),revoke_reason='Synthetic preupgrade revocation')
  currency=put(c,'company_currencies',company_id=co,code='USD',display_name='Synthetic dollar',symbol='$',decimal_places=2,active=True,is_base=True,cash_accepted=True,card_accepted=True,mobile_accepted=True)
  put(c,'company_settings',company_id=co,currency_code='USD',currency_symbol='$',base_currency_id=currency,tax_rate=0,shift_enforcement_enabled=False,reporting_timezone='UTC')
  shift=put(c,'cashier_shifts',**context,device_id=device,employee_id=employee,opened_pos_session_id=session,shift_number='SYN-RICH-OPEN',status='open',opened_at=now-timedelta(hours=2),open_idempotency_key='synthetic-rich-open',business_name_snapshot='Rich release',shop_name_snapshot='Rich shop',branch_name_snapshot='Rich branch',register_name_snapshot='Retained register',cashier_name_snapshot='Rich cashier',base_currency_code_snapshot='USD')
  customer=put(c,'customers',company_id=co,customer_code='SYN-RICH-CREDIT',name='Synthetic credit customer',credit_enabled=True,unlimited_credit=False,credit_limit=100,credit_terms_days=30)
  product=put(c,'products',company_id=co,name='Rich stock',selling_price=Decimal('12.50'),cost_price=Decimal('3.25'),stock_qty=98,track_inventory=True,active=True,deleted=False,product_type='standard',units_per_purchase=1)
  put(c,'inventory_balances',**context,product_id=product,quantity=98,reorder_level=0,active=True)
  salecontext={**context,'device_id':device,'employee_id':employee,'shift_id':shift,'base_currency_code':'USD','payment_currency_code':'USD','status':'completed','tax_amount':0,'tax_rate':0}
  cash=put(c,'sales',**salecontext,client_sale_id=uuid4(),receipt_number='SYN-RICH-CASH',subtotal_amount=25,total_amount=25,payment_method='cash',payment_amount_original=25,tendered_amount_original=30,change_amount_original=5)
  credit=put(c,'sales',**salecontext,client_sale_id=uuid4(),receipt_number='SYN-RICH-CREDIT',customer_id=customer,subtotal_amount=10,total_amount=10,payment_method='credit')
  refund=put(c,'sales',**salecontext,client_sale_id=uuid4(),receipt_number='SYN-RICH-REFUND',original_sale_id=cash,subtotal_amount=Decimal('-12.50'),total_amount=Decimal('-12.50'),payment_method='cash',payment_amount_original=Decimal('-12.50'))
  for sale,qty,price,total in [(cash,2,Decimal('12.50'),25),(credit,1,10,10),(refund,-1,Decimal('12.50'),Decimal('-12.50'))]:put(c,'sale_items',sale_id=sale,product_id=product,product_name='Rich stock',quantity=qty,unit_price=price,line_total=total)
  for kind,qty,before,after,ref in [('opening_stock',100,0,100,'SYN-OPEN'),('sale',2,100,98,'SYN-RICH-CASH'),('sale',1,98,97,'SYN-RICH-CREDIT'),('refund',1,97,98,'SYN-RICH-REFUND')]:put(c,'inventory_movements',**context,product_id=product,product_name='Rich stock',movement_type=kind,quantity=qty,before_qty=before,after_qty=after,unit_cost=Decimal('3.25'),reference=ref)
  debt=put(c,'credit_receivables',**context,sale_id=credit,customer_id=customer,cashier_employee_id=employee,device_id=device,shift_id=shift,currency_code='USD',original_amount=10,amount_settled=3,outstanding_balance=7,due_date=date.today()+timedelta(days=30),status='partially_paid')
  put(c,'credit_settlements',**context,receivable_id=debt,customer_id=customer,actor_user_id=user,cashier_employee_id=employee,device_id=device,shift_id=shift,amount=3,payment_method='cash',received_at=now,idempotency_key='SYN-RICH-COLLECTION',receipt_number='SYN-RICH-COLLECT')
  station=put(c,'printer_stations',**context,device_id=device,name='Synthetic pending printer',purpose='receipt',transport='system',address='',paper_width='80mm',active=True,auto_print=False)
  payload={'kind':'receipt','sale_id':str(cash),'original_amount':'25.00','synthetic':True}
  job=put(c,'print_jobs',company_id=co,station_id=station,sale_id=cash,requested_employee_id=employee,request_key='SYN-RICH-PENDING-OUTPUT',kind='receipt',payload=payload,payload_hash=h(payload),status='pending',attempts=0)
  queued={'client_sale_id':str(uuid4()),'company_id':str(co),'branch_id':str(branch),'device_id':str(device),'employee_id':str(employee),'shift_id':str(shift),'items':[{'product_id':str(product),'quantity':'1'}],'payment_method':'cash','amount_received':'20','original_epoch':0,'synthetic':True}
  put(c,'offline_sale_resolutions',company_id=co,client_sale_id=UUID(queued['client_sale_id']),original_shift_id=shift,original_employee_id=employee,original_device_id=device,action='retain_quarantined',reason='Synthetic retained queue; no stock posting',payload_sha256=h(queued),payload_snapshot=queued,idempotency_key='SYN-RICH-QUARANTINE',resolved_by_user_id=user,resolver_name_snapshot='Synthetic owner')
  ids=dict(company=co,user=user,shop=shop,branch=branch,device=device,employee=employee,session=session,revoked=revoked,product=product,cash=cash,credit=credit,refund=refund,shift=shift,print_job=job)
 root=ROOT/('qualification-rich' if DB.endswith('_qualification') else 'rich');root.mkdir(mode=0o700,exist_ok=True)
 (root/'ids.json').write_text(json.dumps(ids,default=str,indent=2));(root/'retained-browser-queue.json').write_text(json.dumps({'state':'quarantined','original_request':queued,'acknowledged':False},sort_keys=True));print('Synthetic rich corpus committed; no application posting acceptance claimed')
else:
 with e.connect() as c:
  c.exec_driver_sql('SET TRANSACTION READ ONLY');assert c.exec_driver_sql('SHOW transaction_read_only').scalar_one()=='on'
  result={}
  for name,query,expected in [
   ('sales','SELECT sum(total_amount)::text FROM sales','22.50'),('collections','SELECT sum(amount)::text FROM credit_settlements','3.00'),('debt','SELECT sum(outstanding_balance)::text FROM credit_receivables','7.00'),('stock','SELECT sum(quantity)::text FROM inventory_balances','98.000'),('shifts',"SELECT count(*) FROM cashier_shifts WHERE status='open'",1),('revoked',"SELECT count(*) FROM pos_sessions WHERE revoked_at IS NOT NULL",1),('pending_output',"SELECT count(*) FROM print_jobs WHERE status='pending'",1),('quarantined',"SELECT count(*) FROM offline_sale_resolutions WHERE action='retain_quarantined'",1)]:
   value=c.exec_driver_sql(query).scalar_one();assert value==expected,(name,value,expected);result[name]=value
  print(json.dumps(result))
