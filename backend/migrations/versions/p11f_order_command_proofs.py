"""Freeze new order creation/settlement request proofs; no historical backfill."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11f_order_command_proofs'
down_revision = 'p11e_sale_command_receipts'
branch_labels = depends_on = None


def upgrade():
    for prefix in ('creation', 'settlement'):
        op.add_column('commerce_orders', s.Column(prefix+'_payload_hash', s.String(64)))
        op.add_column('commerce_orders', s.Column(prefix+'_actor_type', s.String(10)))
        op.add_column('commerce_orders', s.Column(prefix+'_actor_id', UUID(as_uuid=True)))
    op.execute("""CREATE FUNCTION protect_order_command_proofs() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN
        IF OLD.creation_payload_hash IS NOT NULL OR OLD.settlement_payload_hash IS NOT NULL THEN
          RAISE EXCEPTION 'Order command proof cannot be deleted'; END IF;
        RETURN OLD;
      END IF;
      IF OLD.creation_payload_hash IS NOT NULL AND ROW(NEW.creation_payload_hash,NEW.creation_actor_type,NEW.creation_actor_id)
        IS DISTINCT FROM ROW(OLD.creation_payload_hash,OLD.creation_actor_type,OLD.creation_actor_id) THEN
        RAISE EXCEPTION 'Order creation proof is immutable'; END IF;
      IF OLD.settlement_payload_hash IS NOT NULL AND ROW(NEW.settlement_payload_hash,NEW.settlement_actor_type,NEW.settlement_actor_id)
        IS DISTINCT FROM ROW(OLD.settlement_payload_hash,OLD.settlement_actor_type,OLD.settlement_actor_id) THEN
        RAISE EXCEPTION 'Order settlement proof is immutable'; END IF;
      RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER order_command_proofs BEFORE UPDATE OR DELETE ON commerce_orders FOR EACH ROW EXECUTE FUNCTION protect_order_command_proofs()')


def downgrade():
    raise RuntimeError('Order replay and identity revocation must survive rollback; use reviewed forward recovery')
