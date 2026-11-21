"""Require original tender debt evidence for every split credit note insert."""
from alembic import op
revision='p11y_split_credit_note_guard'
down_revision='p11x_split_refund_allocations'
branch_labels=depends_on=None
def upgrade():
    op.execute('''CREATE FUNCTION validate_split_credit_note() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE method text; BEGIN
      SELECT payment_method INTO method FROM sales WHERE id=NEW.refund_sale_id;
      IF method='split_refund' AND
       (SELECT COALESCE(sum(amount),0) FROM credit_refund_adjustments WHERE refund_sale_id=NEW.refund_sale_id)<>
       (SELECT COALESCE(sum(amount_base),0) FROM sale_tender_refunds WHERE refund_sale_id=NEW.refund_sale_id AND kind='debt_reduction') THEN
        RAISE EXCEPTION 'Split credit note requires original tender debt allocation'; END IF; RETURN NULL; END $$''')
    op.execute('CREATE CONSTRAINT TRIGGER split_credit_note_evidence AFTER INSERT ON credit_refund_adjustments DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_split_credit_note()')
def downgrade():raise RuntimeError('Credit note/tender proof and every identity/revocation/queue safeguard require compatible forward recovery')
