"""add employee permissions and cashier sales

Revision ID: e7b1c5a9d240
Revises: d42f8a9c1b70
"""

from alembic import op, context
import bcrypt
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7b1c5a9d240"
down_revision = "d42f8a9c1b70"
branch_labels = None
depends_on = None


CASHIER_PERMISSIONS = """
'{
  "sales": true,
  "discounts": false,
  "refunds": false,
  "inventory": false,
  "products": false,
  "reports": false,
  "employees": false,
  "settings": false
}'::jsonb
"""

MANAGER_PERMISSIONS = """
'{
  "sales": true,
  "discounts": true,
  "refunds": true,
  "inventory": true,
  "products": true,
  "reports": true,
  "employees": true,
  "settings": false
}'::jsonb
"""

OWNER_PERMISSIONS = """
'{
  "sales": true,
  "discounts": true,
  "refunds": true,
  "inventory": true,
  "products": true,
  "reports": true,
  "employees": true,
  "settings": true
}'::jsonb
"""


def upgrade():
    op.alter_column(
        "employees",
        "pin",
        existing_type=sa.String(length=4),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    op.add_column(
        "employees",
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(CASHIER_PERMISSIONS),
        ),
    )

    op.execute(
        f"""
        UPDATE employees
        SET permissions = {MANAGER_PERMISSIONS}
        WHERE lower(role) = 'manager'
        """
    )

    op.execute(
        f"""
        UPDATE employees
        SET permissions = {OWNER_PERMISSIONS}
        WHERE lower(role) = 'owner'
        """
    )

    bind = op.get_bind()

    employees = [] if context.is_offline_mode() else bind.execute(
        sa.text(
            """
            SELECT id, pin
            FROM employees
            """
        )
    ).mappings().all() if not context.is_offline_mode() else []

    for employee in employees:
        existing_pin = employee["pin"] or ""

        if existing_pin.startswith("$2"):
            continue

        hashed_pin = bcrypt.hashpw(
            existing_pin.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

        bind.execute(
            sa.text(
                """
                UPDATE employees
                SET pin = :hashed_pin
                WHERE id = :employee_id
                """
            ),
            {
                "hashed_pin": hashed_pin,
                "employee_id": employee["id"],
            },
        )

    op.add_column(
        "sales",
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "cashier_name",
            sa.String(length=160),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_sales_employee_id",
        "sales",
        ["employee_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_sales_employee_id",
        "sales",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_sales_employee_id",
        "sales",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_sales_employee_id",
        table_name="sales",
    )

    op.drop_column("sales", "cashier_name")
    op.drop_column("sales", "employee_id")
    op.drop_column("employees", "permissions")

    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            UPDATE employees
            SET pin = '0000'
            """
        )
    )

    op.alter_column(
        "employees",
        "pin",
        existing_type=sa.String(length=255),
        type_=sa.String(length=4),
        existing_nullable=False,
    )
