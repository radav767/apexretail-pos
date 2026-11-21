"""Private single-frame decoded raster assets; no filesystem or URL access."""
import base64,binascii,hashlib,io,warnings
from uuid import uuid4
from fastapi import HTTPException,APIRouter,Depends
from fastapi.routing import APIRoute
from sqlalchemy import select,text,func
from app.models import WorkflowRecord
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from .core import WorkflowService,atomic
from .schema import MediaInput
MAX_UPLOAD=512*1024
MAX_OUTPUT=256*1024
MAX_PIXELS=4_000_000

def normalize(data,content_type):
    from PIL import Image,ImageOps,UnidentifiedImageError
    if not data or len(data)>MAX_UPLOAD:raise HTTPException(413,'Logo must contain at most 512 KiB')
    expected={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}[content_type]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data),formats=['PNG','JPEG','WEBP']) as image:
                if image.format!=expected:raise HTTPException(415,'Declared logo type differs from decoded image')
                if image.width>2048 or image.height>2048 or image.width*image.height>MAX_PIXELS:raise HTTPException(413,'Logo dimensions exceed 2048 per side or four million pixels')
                if getattr(image,'n_frames',1)!=1:raise HTTPException(415,'Animated or multi-frame logos are unsupported')
                image.verify()
            with Image.open(io.BytesIO(data),formats=[expected]) as image:
                image.load();clean=ImageOps.exif_transpose(image).convert('RGBA');clean.thumbnail((600,300))
                # Fresh pixels drop source metadata, profiles, EXIF and chunks.
                sanitized=Image.new('RGBA',clean.size);sanitized.paste(clean)
                output=io.BytesIO();sanitized.save(output,format='PNG');payload=output.getvalue()
                if len(payload)>MAX_OUTPUT:raise HTTPException(413,'Normalized logo exceeds 256 KiB')
                return payload,sanitized.width,sanitized.height
    except HTTPException:raise
    except (UnidentifiedImageError,OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(415,'Logo must be a complete supported raster image') from None

class MediaService(WorkflowService):
    @atomic
    async def upload(self,data):
        self.authorize(data.company_id,'business_settings_manage',owner=True)
        if data.branch_id:await self.branch(data.company_id,data.branch_id)
        old,proof=await self.begin(data,'media_upload',data.branch_id)
        if old:return old
        try:raw=base64.b64decode(data.data_base64,validate=True)
        except (ValueError,binascii.Error):raise HTTPException(422,'Invalid logo base64') from None
        png,width,height=normalize(raw,data.content_type)
        await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'document-media-quota:'+str(data.company_id)})
        from .retention import ensure_active
        sha=hashlib.sha256(png).hexdigest()
        duplicate=(await self.db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.branch_id==data.branch_id,WorkflowRecord.kind=='document_media',WorkflowRecord.payload['sha256'].as_string()==sha).order_by(WorkflowRecord.created_at,WorkflowRecord.id).limit(1))).scalar_one_or_none()
        if duplicate:
            await ensure_active(self.db,data.company_id,duplicate.id)
            return await self.finish(data,'media_upload',duplicate,proof)
        count=(await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.kind=='document_media'))).scalar_one()
        if count>=64:raise HTTPException(409,'Tenant logo archive has reached its 64-asset bound; reviewed retention work is required')
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=data.branch_id,kind='document_media',state='validated',payload={'content_type':'image/png','data_base64':base64.b64encode(png).decode('ascii'),'sha256':hashlib.sha256(png).hexdigest(),'width':width,'height':height,'size_bytes':len(png),'validation_version':1})
        self.db.add(row);return await self.finish(data,'media_upload',row,proof)
    async def asset(self,company,media_id,branch):
        self.authorize(company,'business_settings_manage')
        row=await self.record(company,media_id,'document_media')
        from .retention import quota_lock,ensure_active
        await quota_lock(self.db,company)
        await ensure_active(self.db,company,media_id)
        if row.branch_id and row.branch_id!=branch:raise HTTPException(403,'Logo belongs to another branch')
        raw=base64.b64decode(row.payload['data_base64'],validate=True)
        if hashlib.sha256(raw).hexdigest()!=row.payload['sha256']:raise HTTPException(409,'Logo digest requires review')
        return row.payload

class BoundedUploadRoute(APIRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def bounded(request):
            total=0;chunks=[]
            async for chunk in request.stream():
                total+=len(chunk)
                if total>720000:raise HTTPException(413,'Logo upload envelope exceeds 720000 bytes')
                chunks.append(chunk)
            request._body=b''.join(chunks)
            return await handler(request)
        return bounded
router=APIRouter(prefix='/inventory/workflows',tags=['Private document media'],route_class=BoundedUploadRoute)
@router.post('/media')
async def upload(data:MediaInput,db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await MediaService(db,actor).upload(data)
