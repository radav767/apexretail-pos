"""Original actor/register bindings for new immutable stock/tip commands."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11i_stock_command_authority'
down_revision = 'p11h_employee_session_epochs'
branch_labels = depends_on = None


def upgrade():
    for table in ('batch_stock_operations', 'batch_return_inspections', 'tip_entries'):
        op.add_column(table, s.Column('actor_type', s.String(10)))
        op.add_column(table, s.Column('actor_id', UUID(as_uuid=True)))
        op.add_column(table, s.Column('device_id', UUID(as_uuid=True)))
        op.add_column(table, s.Column('assignment_revision', s.Integer))
    # Existing inspection/tip triggers already reject UPDATE/DELETE. Batch
    # operation INSERT-only application grants now have the same DB guarantee.
    op.execute('CREATE TRIGGER batch_stock_operations_immutable BEFORE UPDATE OR DELETE ON batch_stock_operations FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute("""CREATE FUNCTION protect_stock_command_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.action IN ('inventory_count_committed_v1','inventory_transfer_committed_v1') THEN
        RAISE EXCEPTION 'Stock command acknowledgement is immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER stock_command_audit_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION protect_stock_command_audit()')


def downgrade():
    raise RuntimeError('Stock command proofs and every session revocation must survive rollback; use reviewed forward recovery')
