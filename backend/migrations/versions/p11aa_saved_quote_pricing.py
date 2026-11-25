"""Freeze saved quotation pricing and accepted converted sale evidence."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import JSONB
revision='p11aa_saved_quote_pricing'
down_revision='p11z_split_note_ownership'
branch_labels=depends_on=None
def upgrade():
    op.add_column('commerce_orders',s.Column('quotation_pricing',JSONB))
    op.add_column('quotation_commands',s.Column('result',JSONB))
    op.execute('''CREATE FUNCTION freeze_saved_quote_pricing() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.quotation_terms IS NOT NULL AND NEW.quotation_pricing IS DISTINCT FROM OLD.quotation_pricing THEN RAISE EXCEPTION 'Accepted quotation pricing is immutable'; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER saved_quote_pricing_frozen BEFORE UPDATE ON commerce_orders FOR EACH ROW EXECUTE FUNCTION freeze_saved_quote_pricing()')
    op.execute('''CREATE FUNCTION freeze_saved_quote_sale() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF EXISTS(SELECT FROM commerce_orders WHERE sale_id=OLD.id AND quotation_terms->>'version'='2') AND (TG_OP='DELETE' OR (to_jsonb(NEW)-'status'-'reprint_count'-'last_reprinted_at') IS DISTINCT FROM (to_jsonb(OLD)-'status'-'reprint_count'-'last_reprinted_at')) THEN RAISE EXCEPTION 'Accepted quotation sale snapshots are immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER saved_quote_sale_frozen BEFORE UPDATE OR DELETE ON sales FOR EACH ROW EXECUTE FUNCTION freeze_saved_quote_sale()')
    op.execute('''CREATE FUNCTION freeze_saved_quote_items() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP IN ('UPDATE','DELETE') AND EXISTS(SELECT FROM commerce_orders WHERE sale_id=OLD.sale_id AND quotation_terms->>'version'='2') OR TG_OP<>'DELETE' AND EXISTS(SELECT FROM commerce_orders WHERE sale_id=NEW.sale_id AND quotation_terms->>'version'='2') THEN RAISE EXCEPTION 'Accepted quotation sale items are immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER saved_quote_items_frozen BEFORE INSERT OR UPDATE OR DELETE ON sale_items FOR EACH ROW EXECUTE FUNCTION freeze_saved_quote_items()')
def downgrade():raise RuntimeError('Saved pricing and every revocation/queue/transaction/document safeguard require forward recovery')
