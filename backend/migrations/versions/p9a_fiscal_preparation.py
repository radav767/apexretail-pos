"""Additive, uncommissioned fiscal configuration and immutable review records.

No backfill, no historical transaction changes, no automatic fiscal activation.
"""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID

revision = 'p9a_fiscal_preparation'
down_revision = 'p8a_commercial_billing'
branch_labels = None
depends_on = None


def uid(name, target=None, **kw):
    return s.Column(name, UUID(as_uuid=True), *([s.ForeignKey(target)] if target else []), **kw)


def upgrade():
    op.create_table('fiscal_configurations', uid('company_id', 'companies.id', primary_key=True),
                    s.Column('version', s.Integer(), nullable=False), s.Column('settings', s.JSON(), nullable=False),
                    s.Column('updated_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
                    s.CheckConstraint('version > 0', name='ck_fiscal_configuration_version'))
    op.create_table('fiscal_preparations', uid('id', primary_key=True), uid('company_id', 'companies.id', nullable=False),
                    uid('sale_id', 'sales.id', nullable=False), s.Column('snapshot', s.JSON(), nullable=False),
                    s.Column('snapshot_hash', s.String(64), nullable=False),
                    s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
                    s.UniqueConstraint('company_id', 'sale_id', name='uq_fiscal_preparation_sale'))
    op.create_table('fiscal_audit', uid('id', primary_key=True), uid('company_id', 'companies.id', nullable=False),
                    uid('actor_user_id', 'users.id', nullable=False), s.Column('action', s.String(80), nullable=False),
                    s.Column('details', s.JSON(), nullable=False),
                    s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()))
    for table in ('fiscal_preparations', 'fiscal_audit'):
        op.create_index(f'ix_{table}_company_id', table, ['company_id'])
    op.execute("""CREATE FUNCTION protect_fiscal_records() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'Fiscal records are append-only'; END $$""")
    for table in ('fiscal_preparations', 'fiscal_audit'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_fiscal_records()')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT, INSERT, UPDATE ON fiscal_configurations TO apex_user;
        GRANT SELECT, INSERT ON fiscal_preparations, fiscal_audit TO apex_user;
        END IF; END $$""")


def downgrade():
    bind = op.get_bind()
    for table in ('fiscal_configurations', 'fiscal_preparations', 'fiscal_audit'):
        if bind.execute(s.text(f'SELECT EXISTS(SELECT FROM {table})')).scalar():
            raise RuntimeError('Fiscal data exists; reviewed forward recovery required')
    for table in ('fiscal_audit', 'fiscal_preparations', 'fiscal_configurations'):
        op.drop_table(table)
    op.execute('DROP FUNCTION protect_fiscal_records()')
