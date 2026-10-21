from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.auth.dependencies import require_path_owner
from app.db.session import get_db
from .schema import FiscalSettings
from .service import FiscalService

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
