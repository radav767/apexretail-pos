"""Full request proofs for new expense and collection commands only."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11g_financial_command_proofs'
down_revision = 'p11f_order_command_proofs'
branch_labels = depends_on = None


def upgrade():
    for table in ('expenses', 'credit_settlements'):
        op.add_column(table, s.Column('command_hash', s.String(64)))
        op.add_column(table, s.Column('command_actor_type', s.String(10)))
        op.add_column(table, s.Column('command_actor_id', UUID(as_uuid=True)))
        op.add_column(table, s.Column('command_device_revision', s.Integer))
    op.execute("""CREATE FUNCTION protect_financial_command_proof() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN
        IF OLD.command_hash IS NOT NULL THEN RAISE EXCEPTION 'Financial command proof cannot be deleted'; END IF;
        RETURN OLD;
      END IF;
      IF OLD.command_hash IS NOT NULL AND ROW(NEW.command_hash,NEW.command_actor_type,NEW.command_actor_id,
        NEW.command_device_revision,NEW.company_id,NEW.branch_id,NEW.device_id,NEW.idempotency_key)
        IS DISTINCT FROM ROW(OLD.command_hash,OLD.command_actor_type,OLD.command_actor_id,
        OLD.command_device_revision,OLD.company_id,OLD.branch_id,OLD.device_id,OLD.idempotency_key) THEN
        RAISE EXCEPTION 'Financial command proof is immutable'; END IF;
      RETURN NEW; END $$""")
    for table in ('expenses', 'credit_settlements'):
        op.execute(f'CREATE TRIGGER financial_command_proof BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_financial_command_proof()')


def downgrade():
    raise RuntimeError('Financial replay and identity revocation must survive rollback; use reviewed forward recovery')
