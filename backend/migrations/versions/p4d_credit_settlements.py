"""add immutable credit settlements

Revision ID: p4d_credit_settlements
Revises: p4c_customers_receivables
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p4d_credit_settlements"
down_revision: Union[str, None] = "p4c_customers_receivables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_settlements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("receivable_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("cashier_employee_id", sa.UUID(), nullable=True),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(160), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("receipt_number", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_credit_settlements_amount_positive"),
        sa.CheckConstraint("payment_method IN ('cash','card','mobile')", name="ck_credit_settlements_method"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["receivable_id"], ["credit_receivables.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cashier_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_credit_settlements_company_idempotency"),
        sa.UniqueConstraint("receipt_number", name="uq_credit_settlements_receipt"),
    )
    op.create_index("ix_settlements_company_customer_date", "credit_settlements", ["company_id", "customer_id", "received_at"])
    op.create_index("ix_settlements_receivable", "credit_settlements", ["receivable_id"])
    op.execute("""
        CREATE FUNCTION reject_credit_settlement_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'credit settlements are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_credit_settlements_immutable
        BEFORE UPDATE OR DELETE ON credit_settlements
        FOR EACH ROW EXECUTE FUNCTION reject_credit_settlement_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_credit_settlements_immutable ON credit_settlements")
    op.execute("DROP FUNCTION reject_credit_settlement_mutation()")
    op.drop_table("credit_settlements")
