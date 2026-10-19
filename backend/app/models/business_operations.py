"""Unpaid operational documents are separate from the existing financial ledger."""
import uuid
from sqlalchemy import Column, String, Integer, Numeric, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, Index, text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    profile = Column(String(24), nullable=False)
    tip_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))
    service_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))


class DiningTable(Base):
    __tablename__ = "dining_tables"
    __table_args__ = (UniqueConstraint("branch_id", "name", name="uq_dining_table_name"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    name = Column(String(60), nullable=False)
    floor = Column(String(60), nullable=False, default="Main floor")
    seats = Column(Integer, nullable=False, default=4)
    x = Column(Integer, nullable=False, default=0)
    y = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)


class HospitalityRoom(Base):
    __tablename__ = "hospitality_rooms"
    __table_args__ = (UniqueConstraint("branch_id", "name", name="uq_hospitality_room_name"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    name = Column(String(60), nullable=False)
    active = Column(Boolean, nullable=False, default=True)


class GuestAccount(Base):
    __tablename__ = "guest_accounts"
    __table_args__ = (Index("uq_guest_room_active", "room_id", unique=True, postgresql_where=text("active")),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey("hospitality_rooms.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=True)


class CommerceOrder(Base):
    __tablename__ = "commerce_orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    waiter_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"))
    table_id = Column(UUID(as_uuid=True), ForeignKey("dining_tables.id"))
    guest_id = Column(UUID(as_uuid=True), ForeignKey("guest_accounts.id"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    parent_id = Column(UUID(as_uuid=True), ForeignKey("commerce_orders.id"))
    sale_id = Column(UUID(as_uuid=True), ForeignKey("sales.id"), unique=True)
    kind = Column(String(24), nullable=False, default="restaurant")
    status = Column(String(24), nullable=False, default="open")
    version = Column(Integer, nullable=False, default=1)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    number = Column(String(40), nullable=False, unique=True)
    last_dispatch_context = Column(JSONB, nullable=True)
    notes = Column(String(500), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("company_id", "request_id", name="uq_commerce_order_request"),)


class CommerceOrderItem(Base):
    __tablename__ = "commerce_order_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("commerce_orders.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id"))
    category_id = Column(UUID(as_uuid=True))
    name = Column(String(280), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    sent_quantity = Column(Numeric(12, 3), nullable=False, default=0)
    price = Column(Numeric(12, 2), nullable=False)
    unit = Column(String(20), nullable=False)
    notes = Column(String(500), nullable=False, default="")


class KitchenTicket(Base):
    __tablename__ = "kitchen_tickets"
    __table_args__ = (UniqueConstraint("order_id", "station_id", "version", name="uq_kitchen_ticket_revision"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey("commerce_orders.id"), nullable=False)
    station_id = Column(UUID(as_uuid=True), ForeignKey("printer_stations.id"), nullable=False)
    print_job_id = Column(UUID(as_uuid=True), ForeignKey("print_jobs.id"), nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProductBatch(Base):
    __tablename__ = "product_batches"
    __table_args__ = (UniqueConstraint("company_id", "branch_id", "product_id", "code", name="uq_product_batch"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    code = Column(String(80), nullable=False)
    expires_on = Column(Date, nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)


class BatchAllocation(Base):
    __tablename__ = "batch_allocations"
    __table_args__ = (UniqueConstraint("movement_id", "batch_id", name="uq_batch_movement_allocation"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("product_batches.id"), nullable=False)
    movement_id = Column(UUID(as_uuid=True), ForeignKey("inventory_movements.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
