"""Synthetic private-socket migration preservation rehearsal. No production input."""
import argparse, hashlib, json, subprocess, os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal
import sqlalchemy as sa

p=argparse.ArgumentParser();p.add_argument('action',choices=['seed','snapshot','compare','newer']);p.add_argument('--root',required=True);p.add_argument('--database',required=True);p.add_argument('--baseline');a=p.parse_args()
root=Path(a.root);config=json.loads((root/'postgres.json').read_text())
assert a.database in config['databases'] and config['port']==55443
assert a.database.startswith('apex_phase11_release_') or a.database=='apexretail_phase7c_test_phase7e'
assert str(config['root']).startswith('/tmp/apex-phase11-release-pg-')
url=sa.URL.create('postgresql+psycopg2',username='postgres',database=a.database,query={'host':config['root'],'port':str(config['port'])})
e=sa.create_engine(url);m=sa.MetaData();m.reflect(e)
def insert(c,table,**fields):
 t=m.tables[table]
 for col in t.columns:
  if col.name in fields or col.nullable or col.server_default is not None:continue
  if col.foreign_keys:raise AssertionError(f'Explicit synthetic foreign key required: {table}.{col.name}')
  if isinstance(col.type,sa.UUID):fields[col.name]=uuid4()
  elif isinstance(col.type,sa.DateTime):fields[col.name]=datetime.now(timezone.utc)
  elif isinstance(col.type,sa.Boolean):fields[col.name]=False
  elif isinstance(col.type,(sa.Numeric,sa.Integer)):fields[col.name]=0
  elif isinstance(col.type,sa.String):fields[col.name]='synthetic'
  else:raise AssertionError(f'Explicit synthetic value required: {table}.{col.name}')
 c.execute(t.insert().values(**fields));return fields
if a.action=='seed':
 with e.begin() as c:
  assert c.execute(sa.select(sa.func.count()).select_from(m.tables['companies'])).scalar_one()==0
  company=insert(c,'companies',name='Isolated upgrade tenant',owner_email='upgrade@example.invalid',business_type='Retail')['id']
  user=insert(c,'users',company_id=company,email='upgrade@example.invalid',password_hash='not-a-login-hash',role='owner')['id']
  shop=insert(c,'shops',company_id=company,name='Synthetic shop')['id']
  branch=insert(c,'branches',company_id=company,shop_id=shop,name='Synthetic branch')['id']
  product=insert(c,'products',company_id=company,name='Synthetic migration product',selling_price=Decimal('12.50'),cost_price=Decimal('3.25'),stock_qty=Decimal('98'),track_inventory=True,active=True,deleted=False,product_type='standard',units_per_purchase=1)['id']
  sale=insert(c,'sales',company_id=company,shop_id=shop,branch_id=branch,client_sale_id=uuid4(),receipt_number='SYN-UPGRADE-1',subtotal_amount=25,total_amount=25,tax_amount=0,status='completed',payment_method='cash',base_currency_code='USD',payment_currency_code='USD',payment_amount_original=25,tendered_amount_original=30,change_amount_original=5)['id']
  insert(c,'sale_items',sale_id=sale,product_id=product,product_name='Synthetic migration product',quantity=2,unit_price=Decimal('12.50'),line_total=25)
  ids=dict(company=company,user=user,shop=shop,branch=branch,product=product,sale=sale)
 (root/'synthetic-ids.json').write_text(json.dumps(ids,default=str,indent=2))
elif a.action=='newer':
 ids=json.loads((root/'synthetic-ids.json').read_text());ids={k:__import__('uuid').UUID(v) for k,v in ids.items()}
 with e.begin() as c:
  # Deliberately creates new post-backup evidence. This is a DB preservation
  # fixture, not application sale/stock posting or interrupted-deploy acceptance.
  insert(c,'sales',company_id=ids['company'],shop_id=ids['shop'],branch_id=ids['branch'],client_sale_id=uuid4(),receipt_number='SYN-NEWER-2',subtotal_amount=1,total_amount=1,tax_amount=0,status='completed',payment_method='cash')
  c.execute(m.tables['users'].update().where(m.tables['users'].c.id==ids['user']).values(session_version=7))
else:
 baseline=json.loads(Path(a.baseline).read_text()) if a.baseline else None
 snapshot={}
 with e.connect() as c:
  tx=c.begin();c.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');assert c.exec_driver_sql('SHOW transaction_read_only').scalar_one()=='on'
  for name,t in sorted(m.tables.items()):
   if name=='alembic_version' or baseline is not None and name not in baseline:continue
   cols=baseline[name]['columns'] if baseline else [col.name for col in t.columns]
   rows=[json.dumps(dict(row),default=str,sort_keys=True) for row in c.execute(sa.select(*(t.c[col] for col in cols))).mappings()]
   snapshot[name]={'columns':cols,'rows':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
  tx.rollback()
 if a.action=='compare':
  assert snapshot==baseline, [name for name in snapshot if snapshot[name]!=baseline[name]]
  print(json.dumps({'matched_tables':len(snapshot),'matched_rows':sum(x['rows'] for x in snapshot.values()),'original_columns_preserved':True}))
 else:print(json.dumps(snapshot,indent=2,sort_keys=True))
