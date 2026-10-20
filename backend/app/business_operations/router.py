from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Literal
from pydantic import ValidationError
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.core.config import get_settings
from app.subscriptions.service import SubscriptionService
from .service import BusinessService
from .profiles import PROFILES
from .offline import OfflineOrderService
from .batch_stock import BatchStockService
from .schema import BatchStockInput
from .tip_schema import TipConfigInput, TipInput
from .tips import TipService
from .returns import ReturnService, InspectionInput
from .schema import OfflineDraftInput, OfflineEditInput
from .schema import OfflineKitchenInput, OfflineKDSInput, OfflineResolutionInput
from .schema import ProfileInput, TableInput, RoomInput, GuestInput, OrderInput, OrderItemInput, ItemUpdate, VersionInput, MoveInput, SplitInput, MergeInput, SettlementInput, BatchInput, KitchenStateInput

router = APIRouter(prefix="/operations", tags=["business operations"])


def service(db=Depends(get_db), actor=Depends(get_auth_actor)): return BusinessService(db, actor)


async def require_operational_writes(db=Depends(get_db), actor=Depends(get_auth_actor)):
    settings = get_settings()
    await SubscriptionService(db, offline_grace_hours=settings.subscription_offline_grace_hours, provider_name=settings.subscription_provider_name).enforce_writes_allowed(actor.company_id)


@router.post("/offline/drafts", dependencies=[Depends(require_operational_writes)])
async def synchronize_draft(data: OfflineDraftInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db, actor).synchronize(data)


@router.post("/offline/edits", dependencies=[Depends(require_operational_writes)])
async def synchronize_edit(data: OfflineEditInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db, actor).synchronize(data, edit=True)


@router.post("/offline/drafts/recover")
async def recover_draft(data: OfflineDraftInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db, actor).recover(data)


@router.post("/offline/edits/recover")
async def recover_edit(data: OfflineEditInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db, actor).recover(data, edit=True)


@router.get("/offline/capabilities")
async def offline_capabilities(actor=Depends(get_auth_actor)):
    return {"protocol":"restaurant-offline-v2","commands":["drafts","edits","kitchen","kds"],"payments":False}


@router.post("/offline/kitchen",dependencies=[Depends(require_operational_writes)])
async def synchronize_kitchen(data:OfflineKitchenInput,db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db,actor).synchronize(data,action="kitchen")


@router.post("/offline/kds",dependencies=[Depends(require_operational_writes)])
async def synchronize_kds(data:OfflineKDSInput,db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db,actor).synchronize(data,action="kds")


@router.post("/offline/kitchen/recover")
async def recover_kitchen(data:OfflineKitchenInput,db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db,actor).recover(data,action="kitchen")


@router.post("/offline/kds/recover")
async def recover_kds(data:OfflineKDSInput,db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await OfflineOrderService(db,actor).recover(data,action="kds")


def offline_command(kind,command):
    model,action={"drafts":(OfflineDraftInput,"draft"),"edits":(OfflineEditInput,"edit"),
        "kitchen":(OfflineKitchenInput,"kitchen"),"kds":(OfflineKDSInput,"kds")}[kind]
    try:return model.model_validate(command),action
    except ValidationError as error:
        raise HTTPException(422,[{"loc":list(e["loc"]),"msg":e["msg"],"type":e["type"]} for e in error.errors()])


@router.post("/offline/{kind}/review")
async def review_offline(kind:Literal["drafts","edits","kitchen","kds"],data:OfflineResolutionInput,
    db=Depends(get_db),actor=Depends(get_auth_actor)):
    command,action=offline_command(kind,data.command)
    return await OfflineOrderService(db,actor).review(command,action=action)


@router.post("/offline/{kind}/resolve",dependencies=[Depends(require_operational_writes)])
async def resolve_offline(kind:Literal["drafts","edits","kitchen","kds"],data:OfflineResolutionInput,
    db=Depends(get_db),actor=Depends(get_auth_actor)):
    command,action=offline_command(kind,data.command)
    return await OfflineOrderService(db,actor).resolve(command,action=action,observed_version=data.observed_version,
        observed_status=data.observed_status,reason=data.reason)


@router.post("/batches/stock", dependencies=[Depends(require_operational_writes)])
async def batch_stock(data: BatchStockInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await BatchStockService(db, actor).execute(data)


@router.get("/tips/config")
async def tip_config(db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await TipService(db, actor).config()


@router.get("/batches/returns")
async def pending_returns(db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await ReturnService(db, actor).pending()


@router.post("/batches/returns/inspect", dependencies=[Depends(require_operational_writes)])
async def inspect_return(data: InspectionInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await ReturnService(db, actor).inspect(data)


@router.put("/tips/config", dependencies=[Depends(require_operational_writes)])
async def configure_tips(data: TipConfigInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await TipService(db, actor).configure(data)


@router.get("/tips/options")
async def tip_options(db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await TipService(db, actor).options()


@router.post("/tips/entries", dependencies=[Depends(require_operational_writes)])
async def tip_entry(data: TipInput, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await TipService(db, actor).record(data)


@router.get("/tips/reports")
async def tip_report(start: date, end: date, branch_id: UUID | None = None, db=Depends(get_db), actor=Depends(get_auth_actor)):
    return await TipService(db, actor).report(start, end, branch_id)


@router.get("/profiles")
async def profiles(svc=Depends(service)): return PROFILES


@router.get("/profile")
async def profile(svc=Depends(service)): return await svc.profile()


@router.put("/profile")
async def save_profile(data: ProfileInput, svc=Depends(service)): return await svc.save_profile(data)


@router.get("/options")
async def options(svc=Depends(service)): return await svc.options()


@router.get("/tables")
async def tables(svc=Depends(service)): return await svc.tables()


@router.post("/tables")
async def add_table(data: TableInput, svc=Depends(service)): return await svc.save_table(data)


@router.put("/tables/{table_id}")
async def edit_table(table_id: UUID, data: TableInput, svc=Depends(service)): return await svc.save_table(data, table_id)


@router.get("/orders")
async def orders(kind: str | None = Query(default=None, pattern="^(restaurant|room_service|quotation)$"), svc=Depends(service)): return await svc.list_orders(kind)


@router.post("/orders")
async def add_order(data: OrderInput, svc=Depends(service)): return await svc.create_order(data)


@router.get("/orders/{order_id}")
async def get_order(order_id: UUID, svc=Depends(service)): return await svc.order_out(await svc.order(order_id))


@router.post("/orders/{order_id}/items")
async def add_item(order_id: UUID, data: OrderItemInput, svc=Depends(service)): return await svc.add_item(order_id, data)


@router.put("/orders/{order_id}/items/{item_id}")
async def edit_item(order_id: UUID, item_id: UUID, data: ItemUpdate, svc=Depends(service)): return await svc.edit_item(order_id, item_id, data)


@router.post("/orders/{order_id}/send")
async def send(order_id: UUID, data: VersionInput, svc=Depends(service)): return await svc.send_kitchen(order_id, data.version)


@router.post("/orders/{order_id}/transfer")
async def transfer(order_id: UUID, data: MoveInput, svc=Depends(service)): return await svc.move(order_id, data)


@router.post("/orders/{order_id}/split")
async def split(order_id: UUID, data: SplitInput, svc=Depends(service)): return await svc.split(order_id, data)


@router.post("/orders/{order_id}/merge")
async def merge(order_id: UUID, data: MergeInput, svc=Depends(service)): return await svc.merge(order_id, data)


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: UUID, data: VersionInput, svc=Depends(service)): return await svc.cancel(order_id, data.version)


@router.post("/orders/{order_id}/settle")
async def settle(order_id: UUID, data: SettlementInput, svc=Depends(service), _entitlement=Depends(require_operational_writes)): return await svc.settle(order_id, data)


@router.get("/kitchen")
async def kitchen(svc=Depends(service)): return await svc.kitchen()


@router.put("/kitchen/{ticket_id}")
async def kitchen_state(ticket_id: UUID, data: KitchenStateInput, svc=Depends(service)): return await svc.kitchen_state(ticket_id, data.status)


@router.get("/rooms")
async def rooms(svc=Depends(service)): return await svc.rooms()


@router.post("/rooms")
async def add_room(data: RoomInput, svc=Depends(service)): return await svc.save_room(data)


@router.post("/guests")
async def guest(data: GuestInput, svc=Depends(service)): return await svc.open_guest(data)


@router.post("/guests/{guest_id}/close")
async def close_guest(guest_id: UUID, svc=Depends(service)): return await svc.close_guest(guest_id)


@router.put("/rooms/{room_id}")
async def edit_room(room_id: UUID, data: RoomInput, svc=Depends(service)): return await svc.save_room(data, room_id)


@router.get("/guests/{guest_id}/folio")
async def folio(guest_id: UUID, svc=Depends(service)): return await svc.folio(guest_id)


@router.get("/batches")
async def batches(svc=Depends(service)): return await svc.batches()


@router.post("/batches")
async def assign_batch(data: BatchInput, svc=Depends(service)): return await svc.assign_batch(data)


@router.get("/reports")
async def reports(start: date, end: date, svc=Depends(service)): return await svc.reports(start, end)
