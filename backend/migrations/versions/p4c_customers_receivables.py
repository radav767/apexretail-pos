"""add customers and credit receivables

Revision ID: p4c_customers_receivables
Revises: p4b_device_lifecycle
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p4c_customers_receivables"
down_revision: Union[str, None] = "p4b_device_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("customer_code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(60), nullable=True),
        sa.Column("email", sa.String(160), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("credit_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("unlimited_credit", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("credit_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("credit_terms_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("credit_limit IS NULL OR credit_limit >= 0", name="ck_customers_credit_limit_nonnegative"),
        sa.CheckConstraint("credit_terms_days >= 0", name="ck_customers_credit_terms_nonnegative"),
        sa.CheckConstraint("NOT unlimited_credit OR credit_enabled", name="ck_customers_unlimited_requires_enabled"),
        sa.CheckConstraint("NOT unlimited_credit OR credit_limit IS NULL", name="ck_customers_unlimited_has_no_limit"),
        sa.CheckConstraint("NOT credit_enabled OR unlimited_credit OR credit_limit IS NOT NULL", name="ck_customers_enabled_has_policy"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "customer_code", name="uq_customers_company_code"),
    )
    op.create_index("ix_customers_company_name", "customers", ["company_id", "name"])
    op.create_index("ix_customers_company_phone", "customers", ["company_id", "phone"])
    op.add_column("sales", sa.Column("customer_id", sa.UUID(), nullable=True))
    op.add_column("sales", sa.Column("customer_name_snapshot", sa.String(160), nullable=True))
    op.add_column("sales", sa.Column("customer_code_snapshot", sa.String(40), nullable=True))
    op.create_foreign_key("fk_sales_customer_id_customers", "sales", "customers", ["customer_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_sales_customer_id", "sales", ["customer_id"])
    op.create_table(
        "credit_receivables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("sale_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("cashier_employee_id", sa.UUID(), nullable=True),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("original_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_settled", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("outstanding_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), server_default="unpaid", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("original_amount > 0", name="ck_receivables_original_positive"),
        sa.CheckConstraint("amount_settled >= 0 AND amount_settled <= original_amount", name="ck_receivables_settled_range"),
        sa.CheckConstraint("outstanding_balance = original_amount - amount_settled", name="ck_receivables_balance_projection"),
        sa.CheckConstraint("status IN ('unpaid','partially_paid','paid')", name="ck_receivables_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["cashier_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_id", name="uq_credit_receivables_sale"),
    )
    op.create_index("ix_receivables_company_customer", "credit_receivables", ["company_id", "customer_id"])
    op.create_index("ix_receivables_company_branch_due", "credit_receivables", ["company_id", "branch_id", "due_date"])


def downgrade() -> None:
    op.drop_table("credit_receivables")
    op.drop_index("ix_sales_customer_id", table_name="sales")
    op.drop_constraint("fk_sales_customer_id_customers", "sales", type_="foreignkey")
    op.drop_column("sales", "customer_code_snapshot")
    op.drop_column("sales", "customer_name_snapshot")
    op.drop_column("sales", "customer_id")
    op.drop_table("customers")
