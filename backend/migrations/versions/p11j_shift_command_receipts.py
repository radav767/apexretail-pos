"""Full shift/drawer/resolution command proofs; no historical reconstruction."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11j_shift_command_receipts'
down_revision = 'p11i_stock_command_authority'
branch_labels = depends_on = None


def upgrade():
    op.create_table('shift_command_receipts',
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), primary_key=True),
        s.Column('kind', s.String(24), primary_key=True), s.Column('command_key', s.String(100), primary_key=True),
        s.Column('shift_id', UUID(as_uuid=True), s.ForeignKey('cashier_shifts.id', ondelete='RESTRICT'), nullable=False),
        s.Column('movement_id', UUID(as_uuid=True), s.ForeignKey('cashier_shift_cash_movements.id', ondelete='RESTRICT')),
        s.Column('resolution_id', UUID(as_uuid=True), s.ForeignKey('offline_sale_resolutions.id', ondelete='RESTRICT')),
        s.Column('payload_hash', s.String(64), nullable=False), s.Column('actor_type', s.String(10), nullable=False),
        s.Column('actor_id', UUID(as_uuid=True), nullable=False), s.Column('device_id', UUID(as_uuid=True)),
        s.Column('assignment_revision', s.Integer), s.Column('created_at', s.DateTime(timezone=True), server_default=s.func.now(), nullable=False))
    op.execute('CREATE TRIGGER shift_command_receipts_immutable BEFORE UPDATE OR DELETE ON shift_command_receipts FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON shift_command_receipts TO apex_user; END IF; END $$")


def downgrade():
    raise RuntimeError('Shift command proofs and every session revocation must survive rollback; use reviewed forward recovery')
