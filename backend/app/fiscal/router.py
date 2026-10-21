from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from app.auth.dependencies import require_path_owner, get_auth_actor, ensure_company_access
from app.db.session import get_db
from app.models import Sale
from app.models.fiscal import FiscalConfiguration, FiscalPreparation
from app.models.fiscal_protocol import FiscalDocument, FiscalProtocolState, FiscalProtocolEvent
from app.employees.permissions import has_permission
from app.financial_access import enforce_actor_branch
from .schema import FiscalSettings
from .service import FiscalService, digest
from .formatting import receipt_preview

router = APIRouter(prefix='/fiscal/{company_id}', tags=['Fiscal preparation — not commissioned'])


@router.get('/configuration')
async def configuration(company_id: UUID, actor=Depends(require_path_owner), db=Depends(get_db)):
    return await FiscalService(db, actor, company_id).configuration()


@router.put('/configuration')
async def save_configuration(company_id: UUID, data: FiscalSettings, actor=Depends(require_path_owner), db=Depends(get_db)):
    return await FiscalService(db, actor, company_id).save(data)


@router.post('/preparations/{sale_id}')
async def prepare_sale(company_id: UUID, sale_id: UUID, actor=Depends(require_path_owner), db=Depends(get_db)):
    return await FiscalService(db, actor, company_id).prepare(sale_id)


@router.get('/preparations')
async def preparations(company_id: UUID, offset: int = Query(default=0, ge=0), actor=Depends(require_path_owner), db=Depends(get_db)):
    return await FiscalService(db, actor, company_id).preparations(offset)


@router.get('/audit')
async def audits(company_id: UUID, offset: int = Query(default=0, ge=0), actor=Depends(require_path_owner), db=Depends(get_db)):
    return await FiscalService(db, actor, company_id).audits(offset)


@router.get('/runtime')
async def runtime(company_id: UUID, offset: int = Query(default=0, ge=0), actor=Depends(require_path_owner), db=Depends(get_db)):
    return await FiscalService(db, actor, company_id).runtime_status(offset)


@router.get('/documents/{document_id}/preview', response_class=HTMLResponse)
async def preview(company_id: UUID, document_id: UUID, paper: str = Query(default='80mm', pattern='^(58mm|80mm|A4)$'), actor=Depends(require_path_owner), db=Depends(get_db)):
    FiscalService(db, actor, company_id)
    document = (await db.execute(select(FiscalDocument).where(FiscalDocument.company_id == company_id, FiscalDocument.id == document_id))).scalar_one_or_none()
    state = await db.get(FiscalProtocolState, company_id)
    config = await db.get(FiscalConfiguration, company_id)
    if document is None or state is None or config is None or digest(document.payload) != document.payload_hash:
        raise HTTPException(404, 'Fiscal review not found')
    try:
        html = receipt_preview(document.payload, state.data['config'], device_id=config.settings['device_id'], day_no=document.day_no, paper=paper)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return HTMLResponse(html, headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
                                      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/sales/{sale_id}/status')
async def sale_fiscal_status(company_id: UUID, sale_id: UUID, actor=Depends(get_auth_actor), db=Depends(get_db)):
    ensure_company_access(actor, company_id)
    sale = (await db.execute(select(Sale).where(Sale.id == sale_id, Sale.company_id == company_id))).scalar_one_or_none()
    if sale is None:
        raise HTTPException(404, 'Sale not found')
    if actor.actor_type == 'employee':
        enforce_actor_branch(actor, sale.branch_id)
        can_view = has_permission(actor.permissions, 'sales_history_view')
        own_sale = actor.employee is not None and sale.employee_id == actor.employee.id and has_permission(actor.permissions, 'sales_process')
        if not can_view and not own_sale:
            raise HTTPException(403, 'Sale access denied')
    row = (await db.execute(select(FiscalDocument).join(FiscalPreparation, FiscalDocument.preparation_id == FiscalPreparation.id).where(
        FiscalDocument.company_id == company_id, FiscalPreparation.company_id == company_id, FiscalPreparation.sale_id == sale_id))).scalar_one_or_none()
    result = {'configured': await db.get(FiscalConfiguration, company_id) is not None, 'status': 'not_fiscalised',
              'environment': 'uncommissioned', 'certified': False, 'submitted': False}
    if row:
        events = (await db.execute(select(FiscalProtocolEvent).where(FiscalProtocolEvent.company_id == company_id,
            FiscalProtocolEvent.document_id == row.id).order_by(FiscalProtocolEvent.sequence))).scalars().all()
        ack = next((event for event in reversed(events) if event.kind == 'receipt_acknowledged'), None)
        attempted = any(event.kind == 'operation_started' and event.details.get('operation') == 'submitReceipt' for event in events)
        rejected = any(event.kind == 'operation_rejected' for event in events)
        result.update(status='acknowledged_test_validation_unknown' if ack else 'test_submission_requires_review' if attempted else 'test_receipt_queued',
                      environment='test', submitted=True if ack else None if attempted else False)
        if rejected and not ack:
            result['status'] = 'test_submission_rejected_requires_review'
    return result
