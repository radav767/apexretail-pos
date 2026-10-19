from uuid import UUID
from fastapi import APIRouter, Depends
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from .schema import StationInput, JobInput, ClaimInput, ResultInput, RetryInput, OfflineReviewInput
from .service import PrintingService
from .service import permit
from app.financial_access import enforce_actor_company
from app.models import Branch, Device, Shop, Product, Category
from sqlalchemy import select

router = APIRouter(prefix="/printing", tags=["printing"])


def service(db=Depends(get_db), actor=Depends(get_auth_actor)):
    return PrintingService(db, actor)


@router.get("/options/{company_id}")
async def options(company_id: UUID, svc=Depends(service)):
    enforce_actor_company(svc.actor, company_id)
    permit(svc.actor, "printers_manage")
    output = {}
    for name, model in (("branches", Branch), ("devices", Device), ("shops", Shop), ("products", Product), ("categories", Category)):
        q = select(model).where(model.company_id == company_id)
        if name in {"branches", "devices"} and svc.actor.actor_type == "employee" and svc.actor.role not in {"owner", "administrator"}:
            q = q.where((model.id if name == "branches" else model.branch_id) == svc.actor.employee.branch_id)
        if name == "devices":
            q = q.where(Device.removed_at.is_(None))
        rows = (await svc.db.execute(q.order_by(model.name).limit(1000))).scalars().all()
        output[name] = [{"id": row.id, "name": row.name,
            **({"shop_id": row.shop_id} if name in {"branches", "devices"} else {}),
            **({"branch_id": row.branch_id} if name == "devices" else {})} for row in rows]
    return output


@router.get("/stations/{company_id}")
async def list_stations(company_id: UUID, svc=Depends(service)):
    return await svc.list_stations(company_id)


@router.post("/stations")
async def create_station(data: StationInput, svc=Depends(service)):
    return await svc.save_station(data)


@router.put("/station/{station_id}")
async def update_station(station_id: UUID, data: StationInput, svc=Depends(service)):
    return await svc.save_station(data, station_id)


@router.post("/station/{station_id}/jobs")
async def enqueue(station_id: UUID, data: JobInput, svc=Depends(service)):
    return await svc.enqueue(station_id, data)


@router.get("/station/{station_id}/jobs")
async def jobs(station_id: UUID, svc=Depends(service)):
    return await svc.list_jobs(station_id)


@router.post("/jobs/{job_id}/claim")
async def claim(job_id: UUID, data: ClaimInput, svc=Depends(service)):
    return await svc.claim(job_id, data)


@router.post("/jobs/{job_id}/result")
async def result(job_id: UUID, data: ResultInput, svc=Depends(service)):
    return await svc.result(job_id, data)


@router.post("/jobs/{job_id}/retry")
async def retry(job_id: UUID, data: RetryInput, svc=Depends(service)):
    return await svc.retry(job_id, data)


@router.post("/offline-review/{sale_id}")
async def offline_review(sale_id: UUID, data: OfflineReviewInput, svc=Depends(service)):
    return await svc.offline_review(sale_id, data)
