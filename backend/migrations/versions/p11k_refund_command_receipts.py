"""Full request/actor/register proof for newly identified refund commands."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11k_refund_command_receipts'
down_revision = 'p11j_shift_command_receipts'
branch_labels = depends_on = None


def upgrade():
    op.create_table('refund_command_receipts',
        s.Column('request_id', UUID(as_uuid=True), primary_key=True),
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), nullable=False),
        s.Column('sale_id', UUID(as_uuid=True), s.ForeignKey('sales.id'), nullable=False, unique=True),
        s.Column('actor_type', s.String(10), nullable=False), s.Column('actor_id', UUID(as_uuid=True), nullable=False),
        s.Column('payload_hash', s.String(64), nullable=False),
        s.Column('branch_id', UUID(as_uuid=True), s.ForeignKey('branches.id'), nullable=False),
        s.Column('device_id', UUID(as_uuid=True), s.ForeignKey('devices.id')),
        s.Column('assignment_revision', s.Integer),
        s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()))
    op.create_index('ix_refund_command_receipts_company_id','refund_command_receipts',['company_id'])
    op.execute('CREATE TRIGGER refund_command_receipts_immutable BEFORE UPDATE OR DELETE ON refund_command_receipts FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON refund_command_receipts TO apex_user; END IF; END $$")


def downgrade():
    raise RuntimeError('Refund command proofs and every session revocation must survive rollback; use reviewed forward recovery')
