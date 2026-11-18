"""Append-only proof for new sale commands; never guess legacy request bodies."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11e_sale_command_receipts'
down_revision = 'p11d_backoffice_handoff'
branch_labels = depends_on = None


def upgrade():
    op.create_table('sale_command_receipts', s.Column('client_sale_id', UUID(as_uuid=True), primary_key=True),
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), nullable=False),
        s.Column('sale_id', UUID(as_uuid=True), s.ForeignKey('sales.id'), nullable=False, unique=True),
        s.Column('actor_type', s.String(10), nullable=False), s.Column('actor_id', UUID(as_uuid=True), nullable=False),
        s.Column('payload_hash', s.String(64), nullable=False),
        s.Column('branch_id', UUID(as_uuid=True), s.ForeignKey('branches.id'), nullable=False),
        s.Column('device_id', UUID(as_uuid=True), s.ForeignKey('devices.id')), s.Column('assignment_revision', s.Integer()),
        s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
        s.CheckConstraint("actor_type IN ('user','employee')", name='ck_sale_command_actor'))
    op.create_index('ix_sale_command_receipts_company_id', 'sale_command_receipts', ['company_id'])
    op.execute("""CREATE FUNCTION protect_sale_command_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      RAISE EXCEPTION 'Sale command receipts are immutable'; END $$""")
    op.execute('CREATE TRIGGER sale_command_receipt_immutable BEFORE UPDATE OR DELETE ON sale_command_receipts FOR EACH ROW EXECUTE FUNCTION protect_sale_command_receipt()')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
      GRANT SELECT,INSERT ON sale_command_receipts TO apex_user;
      END IF; END $$""")


def downgrade():
    raise RuntimeError('Sale replay and revocation evidence must survive rollback; use reviewed forward recovery')
