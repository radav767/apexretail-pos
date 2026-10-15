"""reconcile automatic shifts and immutable Z report snapshots

Revision ID: p5f_phase4_shift_z
Revises: p5e_settlement_tender_change
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5f_phase4_shift_z"
down_revision: Union[str, None] = "p5e_settlement_tender_change"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for name in (
        "business_name_snapshot", "shop_name_snapshot", "branch_name_snapshot",
        "register_name_snapshot", "cashier_name_snapshot",
    ):
        op.add_column("cashier_shifts", sa.Column(name, sa.String(160), nullable=True))
    op.add_column("cashier_shifts", sa.Column("base_currency_code_snapshot", sa.String(8), nullable=True))
    for name in ("cash_refunds_base", "refunds_base", "cash_in_base", "cash_out_base"):
        op.add_column("cashier_shifts", sa.Column(name, sa.Numeric(14, 2), nullable=True))
    op.add_column("cashier_shifts", sa.Column("closed_by_user_id", sa.UUID(), nullable=True))
    op.add_column("cashier_shifts", sa.Column("closed_by_employee_id", sa.UUID(), nullable=True))
    op.add_column("cashier_shifts", sa.Column("closing_user_name_snapshot", sa.String(160), nullable=True))
    op.add_column("cashier_shifts", sa.Column("report_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_cashier_shifts_closed_by_user", "cashier_shifts", "users", ["closed_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_cashier_shifts_closed_by_employee", "cashier_shifts", "employees", ["closed_by_employee_id"], ["id"], ondelete="RESTRICT")

    # Existing identity relationships are authoritative. Snapshotting their
    # display values does not create or change any historical association.
    op.execute("ALTER TABLE cashier_shifts DISABLE TRIGGER trg_cashier_shifts_protect")
    op.execute("""
        UPDATE cashier_shifts s SET
          business_name_snapshot=c.name,
          shop_name_snapshot=sh.name,
          branch_name_snapshot=b.name,
          register_name_snapshot=COALESCE(d.friendly_name,d.name,'Register ' || d.pos_number::text),
          cashier_name_snapshot=e.name,
          base_currency_code_snapshot=cc.code
        FROM companies c, shops sh, branches b, devices d, employees e,
             company_settings cs, company_currencies cc
        WHERE c.id=s.company_id AND sh.id=s.shop_id AND b.id=s.branch_id
          AND d.id=s.device_id AND e.id=s.employee_id
          AND cs.company_id=s.company_id AND cc.id=cs.base_currency_id
    """)
    # Deliberately do not backfill closing actor or report-generation fields.
    # Phase 3 did not record those facts, and inferring them would fabricate
    # historical audit evidence. Legacy reports therefore identify these
    # values as unknown while all newly closed shifts snapshot them exactly.
    op.execute("ALTER TABLE cashier_shifts ENABLE TRIGGER trg_cashier_shifts_protect")
    for name in (
        "business_name_snapshot", "shop_name_snapshot", "branch_name_snapshot",
        "register_name_snapshot", "cashier_name_snapshot", "base_currency_code_snapshot",
    ):
        op.alter_column("cashier_shifts", name, nullable=False)

    # Extend the deployed Phase 3 ledger. These columns remain nullable for
    # legacy rows because inventing a historical exchange-rate snapshot would
    # be financially incorrect. New movements populate both values when an
    # authoritative effective rate exists; physical-currency accounting never
    # blocks merely because a base conversion is unavailable.
    op.add_column("cashier_shift_cash_movements", sa.Column("base_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("cashier_shift_cash_movements", sa.Column("exchange_rate_snapshot", sa.Numeric(20, 10), nullable=True))
    op.create_check_constraint(
        "ck_shift_cash_movement_rate_positive",
        "cashier_shift_cash_movements",
        "exchange_rate_snapshot IS NULL OR exchange_rate_snapshot > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_shift_cash_movement_rate_positive", "cashier_shift_cash_movements", type_="check")
    op.drop_column("cashier_shift_cash_movements", "exchange_rate_snapshot")
    op.drop_column("cashier_shift_cash_movements", "base_amount")
    op.drop_constraint("fk_cashier_shifts_closed_by_employee", "cashier_shifts", type_="foreignkey")
    op.drop_constraint("fk_cashier_shifts_closed_by_user", "cashier_shifts", type_="foreignkey")
    for name in (
        "report_generated_at", "closing_user_name_snapshot", "closed_by_employee_id",
        "closed_by_user_id", "cash_out_base", "cash_in_base", "refunds_base",
        "cash_refunds_base", "base_currency_code_snapshot", "cashier_name_snapshot", "register_name_snapshot",
        "branch_name_snapshot", "shop_name_snapshot", "business_name_snapshot",
    ):
        op.drop_column("cashier_shifts", name)
