import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CashierShift(Base):
    __tablename__ = "cashier_shifts"
    __table_args__ = (
        CheckConstraint("status IN ('open','closed')", name="ck_cashier_shifts_status"),
        CheckConstraint("(status='open' AND closed_at IS NULL) OR (status='closed' AND closed_at IS NOT NULL)", name="ck_cashier_shifts_closed_state"),
        UniqueConstraint("company_id", "open_idempotency_key", name="uq_cashier_shifts_open_key"),
        UniqueConstraint("company_id", "close_idempotency_key", name="uq_cashier_shifts_close_key"),
        Index("uq_cashier_shifts_open_employee", "employee_id", unique=True, postgresql_where=text("status = 'open'")),
        Index("uq_cashier_shifts_open_device", "device_id", unique=True, postgresql_where=text("status = 'open'")),
        Index("ix_cashier_shifts_company_opened", "company_id", "opened_at"),
        Index("ix_cashier_shifts_company_branch_opened", "company_id", "branch_id", "opened_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shift_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    opened_pos_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pos_sessions.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    tips_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opening_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    closing_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    close_idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gross_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    net_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost_of_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    gross_profit_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    discounts_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    card_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    mobile_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    credit_sales_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_settlements_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    card_settlements_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    mobile_settlements_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_expenses_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    noncash_expenses_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_refunds_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    refunds_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_in_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_out_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    business_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    shop_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    branch_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    register_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    cashier_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    base_currency_code_snapshot: Mapped[str] = mapped_column(String(8), nullable=False)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    closed_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True)
    closing_user_name_snapshot: Mapped[str | None] = mapped_column(String(160), nullable=True)
    report_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CashierShiftCurrencySnapshot(Base):
    __tablename__ = "cashier_shift_currency_snapshots"
    __table_args__ = (
        UniqueConstraint("shift_id", "currency_code", name="uq_shift_currency_code"),
        CheckConstraint("opening_float >= 0", name="ck_shift_currency_opening_nonnegative"),
        CheckConstraint("counted_cash IS NULL OR counted_cash >= 0", name="ck_shift_currency_counted_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    company_currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_currencies.id", ondelete="RESTRICT"), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    currency_name_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    currency_symbol_snapshot: Mapped[str] = mapped_column(String(10), nullable=False)
    decimal_places_snapshot: Mapped[int] = mapped_column(nullable=False)
    cash_accepted_snapshot: Mapped[bool] = mapped_column(nullable=False)
    card_accepted_snapshot: Mapped[bool] = mapped_column(nullable=False)
    mobile_accepted_snapshot: Mapped[bool] = mapped_column(nullable=False)
    opening_float: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_sales: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cash_refunds: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cash_settlements: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cash_expenses: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cash_in: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cash_out: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    variance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CashierShiftCashMovement(Base):
    __tablename__ = "cashier_shift_cash_movements"
    __table_args__ = (
        CheckConstraint("movement_type IN ('cash_in','cash_out')", name="ck_shift_cash_movement_type"),
        CheckConstraint("amount > 0", name="ck_shift_cash_movement_positive_amount"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_shift_cash_movement_idempotency"),
        Index("ix_shift_cash_movements_shift_created", "shift_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    exchange_rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
