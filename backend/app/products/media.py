import hashlib,os,uuid
from pathlib import Path
from fastapi import HTTPException,UploadFile
from app.core.config import get_settings
from app.models.product_media import ProductMedia
TYPES={"image/jpeg":(".jpg",lambda b:b.startswith(b"\xff\xd8\xff")),"image/png":(".png",lambda b:b.startswith(b"\x89PNG\r\n\x1a\n")),"image/webp":(".webp",lambda b:len(b)>11 and b[:4]==b"RIFF" and b[8:12]==b"WEBP")}
async def store(repo,company_id,product_id,upload):
    if hasattr(repo, 'require_write'): await repo.require_write(company_id)
    product=await repo.get_product(company_id,product_id)
    if not product: raise HTTPException(404,"Product not found")
    kind=(upload.content_type or "").lower()
    if kind not in TYPES: raise HTTPException(415,"Only JPEG, PNG and WebP images are supported")
    limit=min(get_settings().product_image_max_bytes,5242880); data=await upload.read(limit+1)
    if not data or len(data)>limit: raise HTTPException(413,"Product image is empty or exceeds 5 MB")
    ext,valid=TYPES[kind]
    if not valid(data): raise HTTPException(415,"Image contents do not match the declared type")
    root=Path(get_settings().product_image_root).resolve(); folder=(root/str(company_id)).resolve()
    if root not in folder.parents: raise HTTPException(500,"Invalid media path")
    folder.mkdir(parents=True,exist_ok=True,mode=0o750); media_id=uuid.uuid4(); name=f"{media_id}{ext}"; path=folder/name; tmp=folder/f".{name}.tmp"
    try:
        tmp.write_bytes(data); os.chmod(tmp,0o640); os.replace(tmp,path)
        media=ProductMedia(id=media_id,company_id=company_id,product_id=product_id,storage_name=name,original_name=Path(upload.filename or "image").name[:255],content_type=kind,size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest()); product.image_url=f"/api/products/images/{company_id}/{media_id}"; repo.db.add_all([media,product]); await repo.db.commit()
        return {"id":media_id,"image_url":product.image_url,"sha256":media.sha256,"size_bytes":len(data)}
    except Exception: tmp.unlink(missing_ok=True); path.unlink(missing_ok=True); raise
def path_for(media):
    path=(Path(get_settings().product_image_root).resolve()/str(media.company_id)/media.storage_name).resolve()
    if not path.is_file(): raise HTTPException(404,"Product image not found")
    return path
