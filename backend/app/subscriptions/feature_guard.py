"""Current server policy complements, never replaces, employee permissions."""
async def enforce_request_features(db,actor,request):
    # Sale command replay is authenticated here, then fingerprinted in the
    # transaction service before current-license/module checks for NEW writes.
    if request.method == 'POST' and request.url.path == '/api/sales': return
    from .commercial import enforce_feature,terms_for
    terms=await terms_for(db,actor.company_id)
    if terms is None:return
    path=request.url.path;method=request.method
    # Historical records remain readable after expiration or module changes.
    if method in {'GET','HEAD','OPTIONS'}:
        return
    feature=None
    if '/products/components/' in path:feature='composites'
    elif '/products/variants/' in path:feature='variants'
    elif '/operations/batches' in path:feature='pharmacy'
    elif any('/operations/'+p in path for p in ('rooms','guests')):feature='hospitality'
    elif any('/operations/'+p in path for p in ('orders','tables','kitchen','offline')):
        # Recovery/review is read-only despite using POST to preserve command identity.
        if path.endswith(('/recover','/review','/resolve')):return
        feature='restaurant'
        if '/orders' in path:
            try:body=await request.json()
            except ValueError:body={}
            kind=body.get('kind') if isinstance(body,dict) else None
            parts=path.split('/orders/',1)
            if len(parts)==2:
                from uuid import UUID
                from sqlalchemy import select
                from app.models import CommerceOrder
                try:order_id=UUID(parts[1].split('/')[0])
                except ValueError:order_id=None
                if order_id:
                    kind=(await db.execute(select(CommerceOrder.kind).where(CommerceOrder.id==order_id,CommerceOrder.company_id==actor.company_id))).scalar_one_or_none()
            if kind=='quotation':feature='wholesale'
            elif kind=='room_service':feature='hospitality'
    if feature:await enforce_feature(db,actor.company_id,feature)
    if path=='/api/products' or '/products/import'==path.removeprefix('/api') or path.startswith('/api/inventory/') or method=='PATCH' and path.startswith('/api/products/'):
        try:body=await request.json()
        except ValueError:return
        if isinstance(body,dict):
            rows=body.get('rows',body.get('items',[body]))
            if isinstance(rows,list):
                if any(isinstance(i,dict) and (i.get('variant_id') or i.get('variant_name')) for i in rows):await enforce_feature(db,actor.company_id,'variants')
                if any(isinstance(i,dict) and i.get('product_type') in {'composite','bundle'} for i in rows):await enforce_feature(db,actor.company_id,'composites')
    if path=='/api/sales':
        from sqlalchemy import select
        from app.models import Product
        try:body=await request.json()
        except ValueError:return
        if not isinstance(body,dict) or not isinstance(body.get('items',[]),list):return
        items=body.get('items',[])
        if not all(isinstance(i,dict) for i in items):return
        if any(i.get('variant_id') for i in items):await enforce_feature(db,actor.company_id,'variants')
        ids=[i.get('product_id') for i in items if i.get('product_id')]
        if ids:
            from uuid import UUID
            try:ids=[UUID(v) for v in ids]
            except (ValueError,TypeError,AttributeError):return  # The sale schema supplies the 422 response.
            products=(await db.execute(select(Product.product_type).where(Product.company_id==actor.company_id,Product.id.in_(ids)))).scalars().all()
            if any(p in {'composite','bundle'} for p in products):await enforce_feature(db,actor.company_id,'composites')
