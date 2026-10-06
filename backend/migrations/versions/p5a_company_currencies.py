"""add company currencies and immutable exchange-rate history

Revision ID: p5a_company_currencies
Revises: p4f_product_barcode_unique
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5a_company_currencies"
down_revision: Union[str, None] = "p4f_product_barcode_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_currencies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_base", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("cash_accepted", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("card_accepted", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("mobile_accepted", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decimal_places >= 0 AND decimal_places <= 4", name="ck_company_currencies_decimal_places"),
        sa.CheckConstraint("code = upper(btrim(code)) AND btrim(code) <> ''", name="ck_company_currencies_normalized_code"),
        sa.CheckConstraint("NOT is_base OR active", name="ck_company_currencies_base_active"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_company_currencies_company_code", "company_currencies", ["company_id", "code"], unique=True)
    op.execute("CREATE UNIQUE INDEX uq_company_currencies_one_base ON company_currencies (company_id) WHERE is_base IS TRUE")

    op.create_table(
        "currency_exchange_rates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("currency_id", sa.UUID(), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("foreign_units_per_base", sa.Numeric(20, 10), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("foreign_units_per_base > 0", name="ck_currency_rates_positive"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["currency_id"], ["company_currencies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "currency_id", "effective_at", name="uq_currency_rates_effective_at"),
    )
    op.create_index("ix_currency_rates_company_currency_effective", "currency_exchange_rates", ["company_id", "currency_id", "effective_at"])
    op.execute("""
        CREATE FUNCTION reject_currency_exchange_rate_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'exchange-rate history is immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_currency_exchange_rates_immutable
        BEFORE UPDATE OR DELETE ON currency_exchange_rates
        FOR EACH ROW EXECUTE FUNCTION reject_currency_exchange_rate_mutation()
    """)

    op.add_column("company_settings", sa.Column("base_currency_id", sa.UUID(), nullable=True))
    op.add_column("company_settings", sa.Column("currency_config_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("company_settings", sa.Column("multi_currency_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("company_settings", sa.Column("reporting_timezone", sa.String(80), server_default="Africa/Harare", nullable=False))
    op.create_foreign_key("fk_company_settings_base_currency", "company_settings", "company_currencies", ["base_currency_id"], ["id"], ondelete="RESTRICT")

    # This is configuration-only seeding. No historical transaction is altered.
    op.execute("""
        INSERT INTO company_currencies (
            id, company_id, code, display_name, symbol, decimal_places,
            active, is_base, cash_accepted, card_accepted, mobile_accepted,
            display_order, created_at, updated_at
        )
        SELECT gen_random_uuid(), c.id,
               upper(btrim(COALESCE(NULLIF(cs.currency_code, ''), 'USD'))),
               upper(btrim(COALESCE(NULLIF(cs.currency_code, ''), 'USD'))),
               COALESCE(NULLIF(cs.currency_symbol, ''), '$'),
               LEAST(GREATEST(COALESCE(cs.decimal_places, 2), 0), 4),
               true, true, true, true, true, 0, now(), now()
          FROM companies c
          LEFT JOIN company_settings cs
            ON cs.company_id=c.id AND cs.deleted IS FALSE
    """)
    op.execute("""
        UPDATE company_settings cs
           SET base_currency_id=cc.id
          FROM company_currencies cc
         WHERE cc.company_id=cs.company_id AND cc.is_base IS TRUE
    """)


def downgrade() -> None:
    op.drop_constraint("fk_company_settings_base_currency", "company_settings", type_="foreignkey")
    op.drop_column("company_settings", "reporting_timezone")
    op.drop_column("company_settings", "multi_currency_enabled")
    op.drop_column("company_settings", "currency_config_version")
    op.drop_column("company_settings", "base_currency_id")
    op.execute("DROP TRIGGER trg_currency_exchange_rates_immutable ON currency_exchange_rates")
    op.execute("DROP FUNCTION reject_currency_exchange_rate_mutation()")
    op.drop_table("currency_exchange_rates")
    op.drop_table("company_currencies")
