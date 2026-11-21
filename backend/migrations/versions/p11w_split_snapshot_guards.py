"""Preserve original split monetary/identity/item snapshots through forward recovery."""
from alembic import op
revision='p11w_split_snapshot_guards'
down_revision='p11v_split_tender_evidence'
branch_labels=depends_on=None

def upgrade():
    op.execute('''CREATE OR REPLACE FUNCTION freeze_split_sale_terms() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.payment_method='split' AND
       (to_jsonb(NEW)-'reprint_count'-'last_reprinted_at'-'status') IS DISTINCT FROM
       (to_jsonb(OLD)-'reprint_count'-'last_reprinted_at'-'status') THEN
        RAISE EXCEPTION 'Original split sale snapshots are immutable'; END IF; RETURN NEW; END $$''')
    op.execute('''CREATE FUNCTION freeze_split_sale_items() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE target uuid; BEGIN
      IF TG_OP IN ('UPDATE','DELETE') AND EXISTS(SELECT FROM sales WHERE id=OLD.sale_id AND payment_method='split') THEN RAISE EXCEPTION 'Original split sale items are immutable'; END IF;
      IF TG_OP<>'DELETE' AND EXISTS(SELECT FROM sales WHERE id=NEW.sale_id AND payment_method='split') AND EXISTS(SELECT FROM sale_tenders WHERE sale_id=NEW.sale_id) THEN RAISE EXCEPTION 'Original split sale items cannot be extended after tender evidence'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER split_sale_items_frozen BEFORE INSERT OR UPDATE OR DELETE ON sale_items FOR EACH ROW EXECUTE FUNCTION freeze_split_sale_items()')

def downgrade():raise RuntimeError('Split snapshot evidence and every session/queue/refund safeguard require compatible forward recovery')
