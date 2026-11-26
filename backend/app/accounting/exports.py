"""Bounded read-only reconciliation bundles. No posting or live integration."""
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import HTTPException, Response
from sqlalchemy import text

from app.accounting.tender_flows import SQL, authorized_scope
from app.reports.service import csv_cell
from app.workflows.core import WorkflowService

MAX_ROWS = 10_000
PAGE_SIZE = 200
MAX_BYTES = 16 * 1024 * 1024
# Extend the SAME statement/snapshot as the paged accounting report, without
# joining receipt totals to tenders, items or collections. No current catalog/FX.
EXPORT_SQL = text(str(SQL) + ''',
 (SELECT count(*) FROM scoped_sales) receipt_count,
 (SELECT COALESCE(jsonb_agg(row ORDER BY occurred_at,source_id),'[]'::jsonb) FROM
   (SELECT id source_id,original_sale_id,branch_id,shift_id,created_at occurred_at,receipt_number,
    CASE WHEN original_sale_id IS NULL THEN 'sale' ELSE 'refund' END kind,
    base_currency_code base_code,subtotal_amount::text subtotal,tax_amount::text tax,
    total_amount::text billed,discount_amount::text discount
    FROM scoped_sales ORDER BY created_at,id LIMIT :limit) row) receipts
''')
EVENT_NUMBERS = frozenset(('applied_base','debt_delta','original_net','tender','change','rate','converted_net','converted_tender','converted_change','allocation_variance','tender_change_variance','drawer_valuation'))
RECEIPT_NUMBERS = frozenset(('subtotal','tax','billed','discount'))
EVENT_FIELDS = ('event_id','kind','source_id','branch_id','shift_id','occurred_at','receipt_number','base_code','method','currency_code',*sorted(EVENT_NUMBERS),'unknown_provenance','original_units_known')
RECEIPT_FIELDS = ('source_id','original_sale_id','kind','branch_id','shift_id','occurred_at','receipt_number','base_code','subtotal','tax','billed','discount')


def csv_bytes(rows, fields, numbers):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerow(fields)
    for row in rows:
        # Only typed, finite numeric columns bypass text-formula neutralisation.
        cells = []
        for key in fields:
            value = row.get(key)
            if key in numbers and value is not None:
                number = Decimal(str(value))
                if not number.is_finite():
                    raise HTTPException(409,'Non-finite historical amount requires review')
                cells.append(format(number,'f'))
            else:
                cells.append(csv_cell(value))
        writer.writerow(cells)
    return stream.getvalue().encode('utf-8')


def package(snapshot):
    """Deterministic bytes for the supplied snapshot; no server-side persistence."""
    files = {}
    files['snapshot.json'] = json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    for name, rows, fields, numbers in (
        ('events',snapshot['events'],EVENT_FIELDS,EVENT_NUMBERS),
        ('receipts',snapshot['receipts'],RECEIPT_FIELDS,RECEIPT_NUMBERS),
    ):
        for offset in range(0,max(1,len(rows)),PAGE_SIZE):
            files[f'{name}-{offset//PAGE_SIZE+1:04d}.csv'] = csv_bytes(rows[offset:offset+PAGE_SIZE],fields,numbers)
    totals = defaultdict(lambda: defaultdict(Decimal))
    for row in snapshot['receipts']:
        group = totals[(row['base_code'],row['kind'])]
        group['receipts'] += 1
        for key in ('billed','tax'):
            group[key] += Decimal(row[key])
    receipt_totals = [dict(base_code=code,kind=kind,**{k:str(v) for k,v in amounts.items()}) for (code,kind),amounts in sorted(totals.items(),key=lambda p:str(p[0]))]
    files['receipt-totals.csv'] = csv_bytes(receipt_totals,('base_code','kind','receipts','billed','tax'),{'receipts','billed','tax'})
    flows = defaultdict(lambda: defaultdict(Decimal))
    for row in snapshot['events']:
        group = flows[(row['base_code'],row['kind'],row['method'],row['currency_code'])]
        group['event_count'] += 1
        for key in ('applied_base','debt_delta'):
            if row[key] is not None:
                group[key] += Decimal(row[key])
            else:
                group['unknown_'+key] += 1
        for key in ('tender','change','original_net','drawer_valuation','allocation_variance','tender_change_variance'):
            known = row['original_units_known'] if key in ('tender','change','original_net') else not row['unknown_provenance']
            if known and row[key] is not None:
                group['known_'+key] += Decimal(row[key])
            else:
                group['unknown_'+key] += 1
    measures = ('applied_base','debt_delta','tender','change','original_net','drawer_valuation','allocation_variance','tender_change_variance')
    flow_numbers = ('event_count',*(name for key in measures for name in ((key if key in ('applied_base','debt_delta') else 'known_'+key),'unknown_'+key)))
    flow_rows = [dict(base_code=code,kind=kind,method=method,currency_code=currency,**{key:str(values[key]) if key in values or key.startswith('unknown_') else None for key in flow_numbers}) for (code,kind,method,currency),values in sorted(flows.items(),key=lambda p:str(p[0]))]
    files['flow-totals.csv'] = csv_bytes(flow_rows,('base_code','kind','method','currency_code',*flow_numbers),set(flow_numbers))
    manifest = {
        'contract_version':'reconciliation-export-v1','page_size':PAGE_SIZE,
        'event_count':snapshot['event_count'],'receipt_count':snapshot['receipt_count'],
        'files':{name:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in files.items()},
        'numeric_event_columns':sorted(EVENT_NUMBERS),'numeric_receipt_columns':sorted(RECEIPT_NUMBERS),
        'notes':[
            'Read-only recorded ledger snapshot; no live accounting integration, posting or provider confirmation.',
            'UTC half-open bounds; receipts by sale/refund creation, collections by their own received_at.',
            'Signed billed revenue/tax are separate from original payments, collections, refunds and debt deltas.',
            'Cash tender/change and frozen FX allocation/tender-change variance are distinct measures; never sum currencies.',
            'Null historical snapshots remain unknown, never zero. Raw JSON is lossless; CSV text is formula-neutralised.',
            'All CSV pages belong to one SQL statement. Preserve the original downloaded bundle; no server retention or resumable snapshot ID.',
            'Receipt discount/subtotal reflect stored evidence; unknown legacy discounts remain null.',
            'Hashes detect changes relative to the supplied manifest; this unsigned bundle is not proof of authenticity.',
        ],
    }
    files['manifest.json'] = json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2).encode('utf-8')
    if sum(map(len,files.values())) > MAX_BYTES:
        raise HTTPException(422,'Export exceeds byte limit; narrow the interval')
    output = io.BytesIO()
    with ZipFile(output,'w') as archive:
        for name,data in files.items():
            info=ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            archive.writestr(info,data)
    return output.getvalue()


async def export_bundle(db,actor,company,start,end,branch=None,shift=None):
    params=await authorized_scope(db,actor,company,start,end,branch,shift)
    result=dict((await db.execute(EXPORT_SQL,{**params,'limit':MAX_ROWS+1,'offset':0})).mappings().one())
    if result['event_count']>MAX_ROWS or result['receipt_count']>MAX_ROWS:
        raise HTTPException(422,'Export exceeds 10000 events or receipts; narrow the interval')
    # Profit/cost are intentionally excluded: this export has revenue/credit authority.
    result.pop('revenue')
    snapshot={
        'contract_version':'reconciliation-export-v1','generated_at':datetime.now(timezone.utc).isoformat(),
        'scope':{key:value.isoformat() if isinstance(value,datetime) else str(value) if value is not None else None for key,value in params.items()},
        'read_consistency':'single_statement','posting_enabled':False,'provider_confirmed':False,**result,
    }
    data=package(snapshot)
    # A reader revoked while the query/package was in flight cannot recover bytes.
    await WorkflowService(db,actor).current_context(company,params['branch'])
    return Response(data,media_type='application/zip',headers={
        'Content-Disposition':'attachment; filename="reconciliation-v1.zip"',
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
        'X-Content-SHA256':hashlib.sha256(data).hexdigest(),
    })
