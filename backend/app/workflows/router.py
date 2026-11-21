from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Depends,Query
from app.db.session import get_db
from app.auth.dependencies import get_auth_actor
from .procurement import ProcurementService
from .schema import SupplierInput,POInput,VersionCommand,ReceiveInput,SupplierReturnInput
router=APIRouter(prefix='/inventory/workflows',tags=['Stock workflows'])
def service(db=Depends(get_db),actor=Depends(get_auth_actor)):return ProcurementService(db,actor)
@router.get('/{company_id}')
async def records(company_id:UUID,kind:Literal['supplier','po','count','template','document'],branch_id:UUID|None=None,limit:int=Query(default=100,ge=1,le=100),offset:int=Query(default=0,ge=0),svc=Depends(service)):
    return await svc.list(company_id,kind,branch_id,limit,offset)
@router.get('/{company_id}/{record_id}')
async def record(company_id:UUID,record_id:UUID,svc=Depends(service)):
    row=await svc.record(company_id,record_id)
    svc.authorize_record(row)
    return svc.view(row)
@router.post('/suppliers')
async def supplier(data:SupplierInput,svc=Depends(service)):return await svc.supplier(data)
@router.post('/purchase-orders')
async def create_po(data:POInput,svc=Depends(service)):return await svc.create_po(data)
@router.post('/purchase-orders/{po_id}/approve')
async def approve(po_id:UUID,data:VersionCommand,svc=Depends(service)):return await svc.approve(po_id,data)
@router.post('/purchase-orders/{po_id}/receive')
async def receive(po_id:UUID,data:ReceiveInput,svc=Depends(service)):return await svc.receive(po_id,data)
@router.post('/purchase-orders/{po_id}/returns')
async def supplier_return(po_id:UUID,data:SupplierReturnInput,svc=Depends(service)):return await svc.supplier_return(po_id,data)

from .schema import CountInput,MeasureInput,ReviewInput
from .counts import CountService
def counter(db=Depends(get_db),actor=Depends(get_auth_actor)):return CountService(db,actor)
@router.post('/counts')
async def create_count(data:CountInput,svc=Depends(counter)):return await svc.create_count(data)
@router.post('/counts/{count_id}/measure')
async def measure(count_id:UUID,data:MeasureInput,svc=Depends(counter)):return await svc.measure(count_id,data)
@router.post('/counts/{count_id}/submit')
async def submit(count_id:UUID,data:VersionCommand,svc=Depends(counter)):return await svc.submit(count_id,data)
@router.post('/counts/{count_id}/recount')
async def recount(count_id:UUID,data:ReviewInput,svc=Depends(counter)):return await svc.recount(count_id,data)
@router.post('/counts/{count_id}/approve')
async def approve_count(count_id:UUID,data:ReviewInput,svc=Depends(counter)):return await svc.approve_count(count_id,data)

from fastapi.responses import HTMLResponse
from .schema import TemplateInput,DocumentInput
from .documents import DocumentService
def documents(db=Depends(get_db),actor=Depends(get_auth_actor)):return DocumentService(db,actor)
@router.post('/templates')
async def publish_template(data:TemplateInput,svc=Depends(documents)):return await svc.publish(data)
@router.post('/documents')
async def create_document(data:DocumentInput,svc=Depends(documents)):return await svc.create_document(data)
@router.get('/documents/{company_id}/{document_id}/html',response_class=HTMLResponse)
async def document_html(company_id:UUID,document_id:UUID,svc=Depends(documents)):
    return HTMLResponse(await svc.read_html(company_id,document_id),headers={'Content-Security-Policy':"default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})

from .schema import PODraftUpdate,SupplierUpdate
@router.put('/purchase-orders/{po_id}')
async def edit_po(po_id:UUID,data:PODraftUpdate,svc=Depends(service)):return await svc.edit_po(po_id,data)
@router.put('/suppliers/{supplier_id}')
async def update_supplier(supplier_id:UUID,data:SupplierUpdate,svc=Depends(service)):return await svc.update_supplier(supplier_id,data)
@router.post('/counts/{count_id}/reject')
async def reject_count(count_id:UUID,data:ReviewInput,svc=Depends(counter)):return await svc.reject_count(count_id,data)
@router.get('/{company_id}/{record_id}/history')
async def history(company_id:UUID,record_id:UUID,limit:int=Query(default=100,ge=1,le=200),offset:int=Query(default=0,ge=0),svc=Depends(service)):
    from sqlalchemy import select
    from app.models import WorkflowCommand
    row=await svc.record(company_id,record_id)
    svc.authorize_record(row)
    return [{'request_id':str(cmd.request_id),'kind':cmd.kind,'result':cmd.result} for cmd in (await svc.db.execute(select(WorkflowCommand).where(WorkflowCommand.company_id==company_id,WorkflowCommand.record_id==record_id).order_by(WorkflowCommand.created_at.desc(),WorkflowCommand.request_id).limit(limit).offset(offset))).scalars()]

@router.post('/purchase-orders/{po_id}/cancel')
async def cancel_po(po_id:UUID,data:ReviewInput,svc=Depends(service)):return await svc.cancel_po(po_id,data)

@router.get('/capabilities/{company_id}/current')
async def capabilities(company_id:UUID,svc=Depends(service)):
    from app.employees.permissions import has_permission
    svc.authorize(company_id)
    owner=svc.actor.role in {'owner','administrator'}
    def allowed(permission):return owner if svc.actor.actor_type=='user' else has_permission(svc.actor.permissions or {},permission)
    from app.products.router import can_view_product_cost
    costs=can_view_product_cost(svc.actor)
    return {'actor_id':str(svc.actor.user.id if svc.actor.user else svc.actor.employee.id),'manage_purchasing':owner,'receive':allowed('inventory_receive') and costs,'return':allowed('inventory_adjust') and costs,'count':allowed('inventory_count'),'approve_count':owner and allowed('inventory_count'),'templates':owner and allowed('business_settings_manage')}

from .schema import CancellationInput
from .recovery import RecoveryService
def recovery(db=Depends(get_db),actor=Depends(get_auth_actor)):return RecoveryService(db,actor)
@router.post('/commands/{request_id}/cancel')
async def cancel_request(request_id:UUID,data:CancellationInput,svc=Depends(recovery)):
    from fastapi import HTTPException
    if request_id!=data.request_id:raise HTTPException(409,'Cancellation request identities differ')
    return await svc.cancel_uncommitted(data)
