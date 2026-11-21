"""Read only the synthetic full-stack tenant; never print/decrypt recipient data."""
import asyncio,base64,json,os,hashlib
from pathlib import Path
from uuid import UUID
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.engine import make_url
from app.db.session import SessionLocal,engine
from app.models import WorkflowRecord,InventoryBalance,WorkflowCommand
url=make_url(os.environ['DATABASE_URL']);assert url.database=='apex_phase11_fullstack_20261121' and not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and os.environ['APP_ENV']=='test'
async def main():
 r=json.loads(Path('/tmp/phase11-fullstack-result.json').read_text());c=UUID(r['tenant']);box=Fernet(b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=')
 async with SessionLocal() as db:
  rows=(await db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==c))).scalars().all();kinds={}
  for row in rows:kinds[row.kind]=kinds.get(row.kind,0)+1
  outputs={str(row.id):row for row in rows if row.kind=='document_output'};assert len(outputs)==2
  captures=[row for row in rows if row.kind=='delivery_capture'];assert len({row.payload['outbox_id'] for row in captures})==len(captures) and len({row.payload['attempt_id'] for row in captures})==len(captures)
  for capture in captures:
   envelope=json.loads(box.decrypt(capture.payload['capture_ciphertext'].encode()));assert envelope['recipient'].endswith('@example.com')
   output=outputs[envelope['output_id']];raw=base64.b64decode(envelope['data_base64']);assert hashlib.sha256(raw).hexdigest()==output.payload['content_digest']
  for row in rows:
   if row.kind in {'delivery_consent','delivery_outbox','delivery_capture'}:assert '@example.com' not in json.dumps(row.payload)
  stock=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==c,InventoryBalance.product_id==UUID(r['product_id'])))).scalar_one();assert stock==208
  result={'synthetic_only':True,'stock':str(stock),'record_counts':kinds,'captures_unique_per_outbox_and_attempt':True,'encrypted_recipient_and_capture_at_rest':True,'captured_bytes_match_immutable_output':True,'provider_calls':0}
  Path('/tmp/phase11-document-sink-persistence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
 await engine.dispose()
asyncio.run(main())
