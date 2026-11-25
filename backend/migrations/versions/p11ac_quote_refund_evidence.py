"""Freeze quotation refunds and constrain cumulative original-currency budgets."""
from alembic import op
revision='p11ac_quote_refund_evidence'
down_revision='p11ab_saved_quote_binding'
branch_labels=depends_on=None

def upgrade():
    op.execute('''CREATE OR REPLACE FUNCTION freeze_saved_quote_sale() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF EXISTS(SELECT FROM commerce_orders WHERE (sale_id=OLD.id OR sale_id=OLD.original_sale_id) AND quotation_terms->>'version'='2')
        AND (TG_OP='DELETE' OR (to_jsonb(NEW)-'status'-'reprint_count'-'last_reprinted_at') IS DISTINCT FROM (to_jsonb(OLD)-'status'-'reprint_count'-'last_reprinted_at'))
      THEN RAISE EXCEPTION 'Accepted quotation sale/refund snapshots are immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute('''CREATE FUNCTION guard_quote_refund_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE target uuid; parent sales%ROWTYPE; original sales%ROWTYPE; terms jsonb; used_base numeric; used_original numeric; bad integer; line_net numeric; line_tax numeric;
      BEGIN
        IF TG_TABLE_NAME='sale_items' THEN target=NEW.sale_id; ELSE target=NEW.id; END IF;
        SELECT * INTO parent FROM sales WHERE id=target;
        IF parent.original_sale_id IS NULL THEN RETURN NULL; END IF;
        SELECT quotation_terms INTO terms FROM commerce_orders WHERE sale_id=parent.original_sale_id AND quotation_terms->>'version'='2';
        IF terms IS NULL THEN RETURN NULL; END IF;
        SELECT * INTO original FROM sales WHERE id=parent.original_sale_id FOR UPDATE;
        IF NOT EXISTS(SELECT FROM refund_command_receipts WHERE sale_id=parent.id AND company_id=parent.company_id)
          OR parent.company_id IS DISTINCT FROM original.company_id OR parent.total_amount>=0
          OR parent.payment_method IS DISTINCT FROM original.payment_method
          OR parent.base_currency_code IS DISTINCT FROM original.base_currency_code
        THEN RAISE EXCEPTION 'Quotation refund needs original scope/method/identified proof'; END IF;
        SELECT coalesce(sum(line_total),0),coalesce(sum(tax_amount),0),count(*) FILTER(WHERE line_total>=0 OR original_sale_item_id IS NULL)
          INTO line_net,line_tax,bad FROM sale_items WHERE sale_id=parent.id;
        IF bad>0 OR line_net IS DISTINCT FROM (CASE WHEN parent.tax_inclusive THEN parent.total_amount ELSE parent.subtotal_amount END) OR line_tax IS DISTINCT FROM parent.tax_amount
        THEN RAISE EXCEPTION 'Quotation refund item evidence differs'; END IF;
        IF original.payment_method='cash' THEN
          SELECT -coalesce(sum(total_amount),0),-coalesce(sum(payment_amount_original),0),
            count(*) FILTER(WHERE company_id IS DISTINCT FROM original.company_id OR payment_method<>'cash'
              OR payment_currency_code IS DISTINCT FROM original.payment_currency_code
              OR exchange_rate_id IS DISTINCT FROM original.exchange_rate_id OR exchange_rate_snapshot IS DISTINCT FROM original.exchange_rate_snapshot
              OR payment_amount_original IS NULL OR payment_amount_original>=0 OR total_amount>=0 OR change_amount_original IS DISTINCT FROM 0)
            INTO used_base,used_original,bad FROM sales WHERE original_sale_id=original.id;
          IF bad>0 OR used_base>original.total_amount OR used_original>original.payment_amount_original
            OR used_original IS DISTINCT FROM round(original.payment_amount_original*used_base/original.total_amount,(terms->>'display_places')::integer)
          THEN RAISE EXCEPTION 'Quotation cumulative original currency refund budget differs'; END IF;
        END IF;
        RETURN NULL; END $$''')
    op.execute('CREATE CONSTRAINT TRIGGER quote_refund_currency_guard AFTER INSERT ON sales DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_quote_refund_evidence()')
    op.execute('CREATE CONSTRAINT TRIGGER quote_refund_item_guard AFTER INSERT ON sale_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_quote_refund_evidence()')
    op.execute('''CREATE FUNCTION freeze_quote_refund_items() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF EXISTS(SELECT FROM sales s JOIN commerce_orders q ON q.sale_id=s.original_sale_id WHERE s.id=OLD.sale_id AND q.quotation_terms->>'version'='2')
        OR TG_OP='UPDATE' AND EXISTS(SELECT FROM sales s JOIN commerce_orders q ON q.sale_id=s.original_sale_id WHERE s.id=NEW.sale_id AND q.quotation_terms->>'version'='2')
      THEN RAISE EXCEPTION 'Quotation refund item evidence is immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER quote_refund_items_frozen BEFORE UPDATE OR DELETE ON sale_items FOR EACH ROW EXECUTE FUNCTION freeze_quote_refund_items()')

def downgrade():raise RuntimeError('Original quotation refund evidence and every revocation/queue safeguard require forward recovery')
