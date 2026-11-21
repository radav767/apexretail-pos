"""Immutable PDF and non-credential authenticated lookup QR from frozen evidence."""
import base64,hashlib,hmac,io,json,unicodedata
from pathlib import Path
from uuid import uuid4,UUID
from fastapi import HTTPException,APIRouter,Depends,Response
from sqlalchemy import select,text
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.models import WorkflowRecord
from .core import WorkflowService,atomic
from .documents import canonical,digest
from .schema import OutputInput,LookupInput
MAX_BYTES=2_000_000
MAX_PAGES=100

def pdf_bytes(template,snapshot):
    import reportlab
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    font='Phase11DejaVuV2'
    font_path=Path(__file__).parent/'fonts/DejaVuSans.ttf'
    font_hash=hashlib.sha256(font_path.read_bytes()).hexdigest()
    if font_hash!='690243adfefe0ce154b547db6205794bd30ac4277275179517a90994f4980648':raise HTTPException(503,'Pinned document font differs; preserve existing output and review')
    if font not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(font,str(font_path)))
    mapping=pdfmetrics.getFont(font).face.charToGlyph
    # Unicode outside the bundled font is explicit review, never replacement.
    value=canonical(snapshot)+canonical(template)
    if len(value)>600000:raise HTTPException(413,'PDF input exceeds bounded layout size')
    texts=[str(snapshot[k]) for k in ('title','identity','notice','source_id')]
    texts.extend(str(v) for r in snapshot['rows'] for v in r.values() if v is not None)
    texts.extend(str(k)+str(v) for k,v in snapshot.get('totals',{}).items())
    texts.extend(str(k)+str(v) for k,v in snapshot.get('payment_rows',[]))
    texts.extend(b.get('text','') for b in template['blocks'])
    if any(ord(c) not in mapping or unicodedata.bidirectional(c) in {'R','AL','AN','RLE','RLO','LRE','LRO','PDF','RLI','LRI','FSI','PDI'} or unicodedata.category(c).startswith('M') for t in texts for c in unicodedata.normalize('NFC',t) if c not in '\n\r\t'):raise HTTPException(422,'PDF font does not cover source text; retain original HTML and review font support')
    width={'58mm':58,'80mm':80,'A4':210}[template['paper']]*72/25.4;height=297*72/25.4
    output=io.BytesIO();canvas=Canvas(output,pagesize=(width,height),pageCompression=1,invariant=1);canvas.setTitle('Recorded business document');canvas.setAuthor('');canvas.setCreator('ApexRetail document renderer 1')
    margin=12;size=8;leading=11;y=height-margin;pages=1
    def page():
        nonlocal y,pages
        if pages>=MAX_PAGES:raise HTTPException(413,'PDF exceeds 100 pages')
        canvas.showPage();pages+=1;y=height-margin;canvas.setFont(font,size)
    canvas.setFont(font,size)
    def line(value):
        nonlocal y
        for paragraph in unicodedata.normalize('NFC',str('Unavailable' if value is None else value)).replace('\t',' ').split('\n'):
            row='';used=0
            for ch in paragraph.replace('\r',''):
                step=pdfmetrics.stringWidth(ch,font,size)
                if row and used+step>width-2*margin:
                    if y<margin+leading:page()
                    canvas.drawString(margin,y,row);y-=leading;row='';used=0
                row+=ch;used+=step
            if y<margin+leading:page()
            canvas.drawString(margin,y,row);y-=leading
    def items():
        line('Item / quantity / amount or review')
        for r in snapshot['rows']:line(str(r['name'])+' | '+str(r.get('quantity','Unavailable'))+' | '+str(r.get('amount','Unavailable')))
    def totals():
        for k,v in snapshot.get('totals',{}).items():line(str(k)+': '+str(v))
        for k,v in snapshot.get('payment_rows',[]):line(str(k)+': '+str(v))
    for key in ('title','identity','notice'):line(snapshot[key])
    placed=set()
    for block in template['blocks']:
        kind=block['kind'];placed.add(kind)
        if kind=='logo':
            asset=template['media'][block['media_id']];raw=base64.b64decode(asset['data_base64'],validate=True)
            if hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise HTTPException(409,'Frozen logo digest differs')
            w=block['width_mm']*72/25.4;h=w*asset['height']/asset['width']
            if h>30*72/25.4:w*=30*72/25.4/h;h=30*72/25.4
            if y-h<margin:page()
            x=margin if block['alignment']=='left' else (width-w)/2 if block['alignment']=='center' else width-margin-w
            canvas.drawImage(ImageReader(io.BytesIO(raw)),x,y-h,width=w,height=h,mask='auto');y-=h+leading
        elif kind=='items':items()
        elif kind=='totals':totals()
        elif kind=='tax':line('Recorded tax: '+str(snapshot.get('totals',{}).get('Tax','Unavailable for this source')))
        else:line(block['text'])
    if 'items' not in placed:items()
    if 'totals' not in placed:totals()
    line('Document source '+snapshot['source_id']);canvas.save();raw=output.getvalue()
    if len(raw)>MAX_BYTES:raise HTTPException(413,'PDF exceeds two million bytes')
    return raw,'reportlab-'+reportlab.Version+(';layout3-split;' if snapshot.get('payment_rows') else ';layout2;')+'DejaVuSans-'+font_hash

def qr_bytes(company,document):
    import qrcode
    from importlib.metadata import version
    payload={'purpose':'authenticated_document_lookup','company_id':str(company),'document_id':str(document.id),'content_digest':document.payload['content_digest']}
    code=qrcode.QRCode(version=None,error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=6,border=4)
    code.add_data(canonical(payload));code.make(fit=True);out=io.BytesIO();code.make_image(fill_color='black',back_color='white').save(out,format='PNG')
    return out.getvalue(),'qrcode-'+version('qrcode')

class OutputService(WorkflowService):
    async def document(self,company,document_id):
        row=await self.record(company,document_id,'document');self.authorize_record(row)
        if digest(row.payload['html'])!=row.payload['content_digest']:raise HTTPException(409,'Stored document digest requires review')
        return row
    def metadata(self,row):
        result=self.view(row);result['payload']={k:v for k,v in row.payload.items() if k!='data_base64'};return result
    @atomic
    async def create(self,data):
        document=await self.document(data.company_id,data.document_id)
        old,proof=await self.begin(data,'document_output',document.branch_id,license_required=False)
        if old:return old
        await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'document-output:{data.company_id}:{document.id}:{data.format}'})
        existing=(await self.db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.kind=='document_output',WorkflowRecord.payload['document_id'].as_string()==str(document.id),WorkflowRecord.payload['format'].as_string()==data.format).limit(1))).scalar_one_or_none()
        if existing:return await self.finish(data,'document_output',existing,proof,self.metadata(existing))
        template=document.payload.get('template_snapshot')
        if not template:template=(await self.record(data.company_id,document.payload['template_id'],'template')).payload
        if data.format=='pdf':raw,engine=pdf_bytes(template,document.payload['source_snapshot']);mime='application/pdf'
        else:raw,engine=qr_bytes(data.company_id,document);mime='image/png'
        if len(raw)>MAX_BYTES:raise HTTPException(413,'Output exceeds safe byte bound')
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=document.branch_id,kind='document_output',state='generated',payload={'document_id':str(document.id),'source_kind':document.payload['source_kind'],'source_digest':document.payload['content_digest'],'format':data.format,'content_type':mime,'engine':engine,'data_base64':base64.b64encode(raw).decode('ascii'),'content_digest':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)})
        self.db.add(row);await self.db.flush();return await self.finish(data,'document_output',row,proof,self.metadata(row))
    async def download(self,company,output_id):
        row=await self.record(company,output_id,'document_output');self.authorize_record(row)
        raw=base64.b64decode(row.payload['data_base64'],validate=True)
        if hashlib.sha256(raw).hexdigest()!=row.payload['content_digest']:raise HTTPException(409,'Stored output digest requires review')
        return row,raw
    async def resolve(self,data):
        row=await self.document(data.company_id,data.document_id)
        if not hmac.compare_digest(row.payload['content_digest'],data.content_digest):raise HTTPException(409,'Lookup digest differs from original document')
        return {'document_id':str(row.id),'company_id':str(row.company_id),'source_kind':row.payload['source_kind'],'content_digest':row.payload['content_digest'],'purpose':'authenticated_document_lookup'}

router=APIRouter(prefix='/inventory/workflows',tags=['Immutable document outputs'])
def service(db=Depends(get_db),actor=Depends(get_auth_actor)):return OutputService(db,actor)
@router.post('/outputs')
async def create(data:OutputInput,svc=Depends(service)):return await svc.create(data)
@router.get('/outputs/{company_id}/{output_id}/download')
async def download(company_id:UUID,output_id:UUID,svc=Depends(service)):
    row,raw=await svc.download(company_id,output_id);ext='pdf' if row.payload['format']=='pdf' else 'png'
    return Response(raw,media_type=row.payload['content_type'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox",'Content-Disposition':f'attachment; filename="document-{row.id}.{ext}"'})
@router.post('/outputs/resolve-lookup')
async def lookup(data:LookupInput,svc=Depends(service)):return await svc.resolve(data)
