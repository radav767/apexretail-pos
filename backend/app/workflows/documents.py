"""No renderer network/files, arbitrary HTML, payment/provider or print actions."""
from uuid import UUID,uuid4
from decimal import Decimal
import hashlib,json,html
from fastapi import HTTPException
from sqlalchemy import select
from app.models import (WorkflowRecord,WorkflowCommand,Sale,SaleItem,CommerceOrder,CommerceOrderItem)
from app.inventory.command_policy import context
from .core import WorkflowService,atomic

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(value):return hashlib.sha256(value.encode('utf8')).hexdigest()
def text(value):return html.escape('Unavailable' if value is None else str(value),quote=True)
PERMISSIONS={'sale':'sales_receipt_reprint','quotation':'quotations_manage','purchase_order':'inventory_receive','supplier_receipt':'inventory_receive','supplier_return':'inventory_adjust','count_sheet':'inventory_count'}

def render(template,snapshot):
    if template.get('layout_version')==2:
        from .layout import render_layout
        return render_layout(template,snapshot)
    width={'58mm':'58mm','80mm':'80mm','A4':'210mm'}[template['paper']]
    parts=['<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
      '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
      '<title>'+text(snapshot['title'])+'</title><style>body{font:12px system-ui;color:#111;background:white;max-width:'+width+';margin:6mm auto;padding:2mm}table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{padding:2mm;overflow-wrap:anywhere;text-align:left;border-bottom:1px solid #ccc}p{white-space:pre-wrap;overflow-wrap:anywhere}@page{margin:6mm}</style></head><body>']
    for block in template['blocks']:
        tag='h1' if block['kind']=='title' else 'p'
        parts.append('<'+tag+'>'+text(block['text'])+'</'+tag+'>')
    parts.append('<h2>'+text(snapshot['title'])+'</h2><p>'+text(snapshot['identity'])+'</p><p>'+text(snapshot['notice'])+'</p>')
    parts.append('<table><thead><tr><th>Item / position</th><th>Quantity</th><th>Amount / review</th></tr></thead><tbody>')
    for row in snapshot['rows']:parts.append('<tr><td>'+text(row['name'])+'</td><td>'+text(row.get('quantity'))+'</td><td>'+text(row.get('amount'))+'</td></tr>')
    parts.append('</tbody></table>')
    for label,value in snapshot.get('totals',{}).items():parts.append('<p>'+text(label)+': '+text(value)+'</p>')
    parts.append('<p>Document source '+text(snapshot['source_id'])+'</p></body></html>')
    return ''.join(parts)

class DocumentService(WorkflowService):
    @atomic
    async def publish(self,data):
        self.authorize(data.company_id,'business_settings_manage',owner=True)
        if data.branch_id:await self.branch(data.company_id,data.branch_id)
        old,proof=await self.begin(data,'template_publish',data.branch_id)
        if old:return old
        previous=await self.record(data.company_id,data.previous_id,'template',True) if data.previous_id else None
        if previous and previous.branch_id!=data.branch_id:raise HTTPException(409,'Template version branch cannot change')
        if previous:
            # Never fork a family invisibly from an older version.
            newer=(await self.db.execute(select(WorkflowRecord.id).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.kind=='template',WorkflowRecord.payload['previous_id'].as_string()==str(previous.id)).limit(1))).first()
            if newer:raise HTTPException(409,'Template version changed; use the latest version')
        record_id=uuid4()
        payload={'family_id':previous.payload['family_id'] if previous else str(record_id),'document_version':previous.payload['document_version']+1 if previous else 1,
            'previous_id':str(previous.id) if previous else None,'paper':data.paper,'blocks':[b.model_dump() for b in data.blocks]}
        kinds=[block['kind'] for block in payload['blocks']]
        if kinds.count('logo')>1 or any(kinds.count(kind)>1 for kind in ('items','totals','tax')):raise HTTPException(422,'Only one logo/items/totals/tax block is allowed')
        if any(kind in {'logo','contact','items','totals','tax'} for kind in kinds):payload['layout_version']=2
        for block in payload['blocks']:
            if block['kind']=='logo':
                from .media import MediaService
                if block['width_mm']>{'58mm':50,'80mm':72,'A4':80}[data.paper]:raise HTTPException(422,'Logo width exceeds safe paper width')
                block['media_id']=str(block['media_id'])
                payload.setdefault('media',{})[block['media_id']]=await MediaService(self.db,self.actor).asset(data.company_id,UUID(block['media_id']),data.branch_id)
        payload['template_digest']=digest(canonical(payload))
        row=WorkflowRecord(id=record_id,company_id=data.company_id,branch_id=data.branch_id,kind='template',state='published',payload=payload)
        self.db.add(row);return await self.finish(data,'template_publish',row,proof)
    async def snapshot(self,data):
        if data.source_kind=='sale':
            row=(await self.db.execute(select(Sale).where(Sale.company_id==data.company_id,Sale.id==data.source_id))).scalar_one_or_none()
            if not row:raise HTTPException(404,'Sale document source not found')
            await context(self.db,self.actor,data.company_id,row.branch_id)
            items=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==row.id).order_by(SaleItem.id))).scalars().all()
            return row.branch_id,{'title':'Refund document' if row.original_sale_id else 'Sale document','identity':row.receipt_number,'source_id':str(row.id),
                'notice':'Snapshot of recorded sale. Rendering does not process payment, print or fiscalise.',
                'rows':[{'name':i.product_name,'quantity':str(i.quantity),'amount':str(i.line_total)} for i in items],
                'totals':{'Status':row.status,'Currency':row.base_currency_code,'Subtotal':str(row.subtotal_amount),'Tax':str(row.tax_amount),'Total':str(row.total_amount)}}
        if data.source_kind=='quotation':
            row=(await self.db.execute(select(CommerceOrder).where(CommerceOrder.company_id==data.company_id,CommerceOrder.id==data.source_id,CommerceOrder.kind=='quotation'))).scalar_one_or_none()
            if not row:raise HTTPException(404,'Quotation source not found')
            await context(self.db,self.actor,data.company_id,row.branch_id)
            items=(await self.db.execute(select(CommerceOrderItem).where(CommerceOrderItem.order_id==row.id).order_by(CommerceOrderItem.id))).scalars().all()
            from app.business_operations.quotations import state
            return row.branch_id,{'title':'Quotation','identity':row.number,'source_id':str(row.id),'notice':'NOT A PAYMENT RECEIPT. '+('Frozen terms; validity '+str(row.quotation_valid_until) if row.quotation_terms else 'Draft estimate; terms not frozen.'),
                'rows':[{'name':i.name,'quantity':str(i.quantity),'amount':str(i.price)+' unit price'} for i in items if i.quantity>0],
                'totals':{'State':state(row),**({'Total':row.quotation_terms['total'],'Tax':row.quotation_terms['tax'],'Currency':row.quotation_terms['currency']} if row.quotation_terms else {})}}
        command=None
        if data.source_kind in {'supplier_receipt','supplier_return'}:
            command=await self.db.get(WorkflowCommand,data.source_id)
            expected='po_receive' if data.source_kind=='supplier_receipt' else 'supplier_return'
            if not command or command.company_id!=data.company_id or command.kind!=expected:raise HTTPException(404,'Original stock receipt not found')
            record=await self.record(data.company_id,command.record_id,'po')
        else:record=await self.record(data.company_id,data.source_id,'po' if data.source_kind=='purchase_order' else 'count')
        await context(self.db,self.actor,data.company_id,record.branch_id)
        if record.kind=='count':
            rows=[{'name':r['name']+(' · '+r.get('lot_code','') if r.get('lot_code') else ''),'quantity':r['measured'],'amount':'Baseline '+str(r['baseline'] if r['baseline'] is not None else 'Unavailable')+'; variance '+str(r.get('variance','unreviewed'))} for r in record.payload['rows']]
        else:
            quantities={r['line_id']:r['quantity'] for r in command.result['lines']} if command and command.kind=='po_receive' else {command.result['line_id']:command.result['quantity']} if command else None
            rows=[{'name':r['name'],'quantity':quantities[r['line_id']] if quantities else r['quantity'],'amount':r['unit_cost']+' per '+r['unit']} for r in record.payload['lines'] if not quantities or r['line_id'] in quantities]
        return record.branch_id,{'title':data.source_kind.replace('_',' ').title(),'identity':str(data.source_id),'source_id':str(data.source_id),'notice':'NOT A PAYMENT RECEIPT. Stock effects belong only to the original identified stock command; this document does not post stock.',
            'rows':rows,'totals':{'State':command.result['order']['state'] if command else record.state,'Opened at':record.payload.get('opened_at','Not applicable')}}
    @atomic
    async def create_document(self,data):
        self.authorize(data.company_id,PERMISSIONS[data.source_kind])
        if data.source_kind in {'purchase_order','supplier_receipt','supplier_return'}:self.costs(data.company_id)
        old,proof=await self.begin(data,'document_render',license_required=False)
        if old:return old
        template=await self.record(data.company_id,data.template_id,'template')
        branch,snapshot=await self.snapshot(data)
        if template.branch_id and template.branch_id!=branch:raise HTTPException(403,'Template is assigned to another branch')
        if len(snapshot['rows'])>5000:raise HTTPException(422,'Document exceeds 5000 rows; use a narrower source')
        rendered=render(template.payload,snapshot)
        if len(rendered.encode('utf8'))>2_000_000:raise HTTPException(413,'Document exceeds safe rendering size')
        payload={'renderer_version':4 if template.payload.get('layout_version')==2 else 1,'template_snapshot':template.payload,'template_id':str(template.id),'template_digest':template.payload['template_digest'],'template_version':template.payload['document_version'],
            'source_kind':data.source_kind,'source_id':str(data.source_id),'source_snapshot':snapshot,'source_digest':digest(canonical(snapshot)),
            'html':rendered,'content_digest':digest(rendered)}
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=branch,kind='document',state='rendered',payload=payload)
        self.db.add(row);return await self.finish(data,'document_render',row,proof)
    async def read_html(self,company,document_id):
        row=await self.record(company,document_id,'document')
        self.authorize(company,PERMISSIONS[row.payload['source_kind']])
        if row.payload['source_kind'] in {'purchase_order','supplier_receipt','supplier_return'}:self.costs(company)
        await context(self.db,self.actor,company,row.branch_id)
        if digest(row.payload['html'])!=row.payload['content_digest']:raise HTTPException(409,'Stored document digest requires review')
        return row.payload['html']
