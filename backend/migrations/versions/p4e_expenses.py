"""add expense categories and posted expenses

Revision ID: p4e_expenses
Revises: p4d_credit_settlements
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p4e_expenses"
down_revision: Union[str, None] = "p4d_credit_settlements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "name", name="uq_expense_categories_company_name"),
    )
    op.create_index("ix_expense_categories_company", "expense_categories", ["company_id"])
    op.create_table(
        "expenses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(160), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        sa.CheckConstraint("payment_method IN ('cash','card','mobile')", name="ck_expenses_method"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"]),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_expenses_company_idempotency"),
    )
    op.create_index("ix_expenses_company_date", "expenses", ["company_id", "occurred_at"])
    op.create_index("ix_expenses_company_branch_date", "expenses", ["company_id", "branch_id", "occurred_at"])
    op.create_index("ix_expenses_company_category_date", "expenses", ["company_id", "category_id", "occurred_at"])
    op.execute("""
        CREATE FUNCTION reject_expense_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'posted expenses are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_expenses_immutable
        BEFORE UPDATE OR DELETE ON expenses
        FOR EACH ROW EXECUTE FUNCTION reject_expense_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_expenses_immutable ON expenses")
    op.execute("DROP FUNCTION reject_expense_mutation()")
    op.drop_table("expenses")
    op.drop_table("expense_categories")
