"""New drafts retain frozen originals; shared lineage owns one conversion."""
from uuid import UUID,uuid4
from fastapi import HTTPException
from sqlalchemy import select,text,func
from app.models import CommerceOrder,CommerceOrderItem,QuotationCommand,Device
from app.sales.commands import actor_identity,fingerprint
from app.printing.service import permit
from .quotations import validate_device

async def lock_lineage(svc,order_id):
    value=(await svc.db.execute(select(CommerceOrder.id,CommerceOrder.kind,CommerceOrder.quotation_root_id).where(CommerceOrder.id==order_id,CommerceOrder.company_id==svc.actor.company_id))).first()
    if not value or value.kind!='quotation':return None
    root=value.quotation_root_id or value.id
    await svc.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'quotation-lineage:{svc.actor.company_id}:{root}'})
    return root

async def superseded(svc,row):
    root=row.quotation_root_id or row.id
    return bool((await svc.db.execute(select(CommerceOrder.id).where(CommerceOrder.company_id==row.company_id,func.coalesce(CommerceOrder.quotation_root_id,CommerceOrder.id)==root,CommerceOrder.quotation_revision>row.quotation_revision,CommerceOrder.quotation_terms.is_not(None)).limit(1))).first())

async def require_current(svc,row,conversion=False):
    if await superseded(svc,row):raise HTTPException(409,'A later sent revision supersedes these terms; retain the original and review the latest quotation')
    if conversion:
        root=row.quotation_root_id or row.id
        converted=(await svc.db.execute(select(CommerceOrder.id).where(CommerceOrder.company_id==row.company_id,func.coalesce(CommerceOrder.quotation_root_id,CommerceOrder.id)==root,CommerceOrder.sale_id.is_not(None)).limit(1))).scalar_one_or_none()
        if converted:raise HTTPException(409,'This quotation lineage already owns a converted sale')

async def revise(svc,order_id,data):
    try:
        identity=actor_identity(svc.actor,svc.actor.company_id);permit(svc.actor,'quotations_manage')
        root=await lock_lineage(svc,order_id)
        await svc.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-quotation:'+str(data.request_id)})
        source=await svc.order(order_id)
        if source.kind!='quotation' or not root:raise HTTPException(400,'Revision requires a quotation')
        device=await svc.db.get(Device,source.device_id,populate_existing=True);validate_device(svc,source,device)
        proof=await svc.db.get(QuotationCommand,data.request_id);digest=fingerprint(data)
        if proof:
            if proof.company_id!=source.company_id or proof.order_id!=source.id or proof.action!='revised' or proof.payload_hash!=digest or not proof.revised_order_id:raise HTTPException(409,'Quotation revision request differs')
            if (proof.actor_type,proof.actor_id)!=(svc.actor.actor_type,identity):raise HTTPException(403,'Original revision belongs to another actor')
            validate_device(svc,source,device,proof.assignment_revision)
            return {**await svc.order_out(await svc.order(proof.revised_order_id)),'quotation_command_ack':str(data.request_id)}
        await svc.require_write('wholesale')
        if source.version!=data.version or not source.quotation_terms or source.status!='open':raise HTTPException(409,'Only an unchanged frozen unconverted quotation may be revised')
        await require_current(svc,source,conversion=True)
        if not data.reason.strip():raise HTTPException(422,'Revision reason is required')
        revision=(await svc.db.execute(select(func.max(CommerceOrder.quotation_revision)).where(CommerceOrder.company_id==source.company_id,func.coalesce(CommerceOrder.quotation_root_id,CommerceOrder.id)==root))).scalar_one() or 0
        if revision>=200:raise HTTPException(422,'Quotation revision chain exceeds 200; reviewed lineage retention is required')
        items=await svc.order_items(source)
        if not 0<len(items)<=500:raise HTTPException(422,'Quotation revision needs 1–500 original positions')
        row=CommerceOrder(id=uuid4(),company_id=source.company_id,branch_id=source.branch_id,device_id=source.device_id,waiter_id=source.waiter_id,customer_id=source.customer_id,parent_id=source.id,quotation_root_id=root,quotation_revision=revision+1,kind='quotation',quotation_status='draft',status='open',version=1,request_id=data.request_id,number='Q-'+uuid4().hex[:16].upper(),notes=source.notes,creation_payload_hash=digest,creation_actor_type=svc.actor.actor_type,creation_actor_id=identity)
        svc.db.add(row);await svc.db.flush()
        for item in items:
            if item.quantity>0:svc.db.add(CommerceOrderItem(order_id=row.id,product_id=item.product_id,variant_id=item.variant_id,category_id=item.category_id,name=item.name,quantity=item.quantity,sent_quantity=0,price=item.price,unit=item.unit,notes=item.notes))
        svc.db.add(QuotationCommand(request_id=data.request_id,company_id=source.company_id,order_id=source.id,actor_type=svc.actor.actor_type,actor_id=identity,payload_hash=digest,device_id=device.id,assignment_revision=device.assignment_revision,action='revised',revised_order_id=row.id))
        svc.audit('quotation_revised',order_id=source.id,revised_order_id=row.id,root_id=root,revision=revision+1,reason=data.reason)
        await svc.commit_operation()
        return {**await svc.order_out(row),'quotation_command_ack':str(data.request_id)}
    except Exception:
        await svc.db.rollback();raise
