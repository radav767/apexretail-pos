"""Prevent unlinking accepted quotation sales to evade immutable evidence."""
from alembic import op
revision='p11ab_saved_quote_binding'
down_revision='p11aa_saved_quote_pricing'
branch_labels=depends_on=None

def upgrade():
    op.execute('''CREATE FUNCTION guard_saved_quote_binding() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE posted sales%ROWTYPE; BEGIN
      IF OLD.quotation_terms->>'version'='2' THEN
        IF OLD.sale_id IS NOT NULL AND (NEW.sale_id IS DISTINCT FROM OLD.sale_id OR NEW.status IS DISTINCT FROM OLD.status
          OR NEW.settlement_payload_hash IS DISTINCT FROM OLD.settlement_payload_hash
          OR NEW.settlement_actor_id IS DISTINCT FROM OLD.settlement_actor_id OR NEW.settlement_actor_type IS DISTINCT FROM OLD.settlement_actor_type)
        THEN RAISE EXCEPTION 'Accepted quotation sale binding and proof are immutable'; END IF;
        IF NEW.sale_id IS NOT NULL AND OLD.sale_id IS NULL THEN
          SELECT * INTO posted FROM sales WHERE id=NEW.sale_id;
          IF NOT FOUND OR NEW.status<>'settled' OR NEW.settlement_payload_hash IS NULL
            OR posted.company_id IS DISTINCT FROM NEW.company_id OR posted.branch_id IS DISTINCT FROM NEW.branch_id
            OR posted.device_id IS DISTINCT FROM NEW.device_id OR posted.customer_id IS DISTINCT FROM NEW.customer_id
            OR posted.total_amount IS DISTINCT FROM (NEW.quotation_terms->>'total')::numeric
            OR posted.tax_amount IS DISTINCT FROM (NEW.quotation_terms->>'tax')::numeric
            OR posted.discount_amount IS DISTINCT FROM (NEW.quotation_terms->>'discount')::numeric
            OR posted.base_currency_code IS DISTINCT FROM NEW.quotation_terms->>'currency'
          THEN RAISE EXCEPTION 'Accepted quotation sale binding differs from frozen terms'; END IF;
        END IF;
      END IF;
      RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER saved_quote_binding_guard BEFORE UPDATE ON commerce_orders FOR EACH ROW EXECUTE FUNCTION guard_saved_quote_binding()')

def downgrade():raise RuntimeError('Quotation binding and all revocation/transaction safeguards require forward recovery')
