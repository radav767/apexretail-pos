"""Bind split credit notes to the original tenant and receivable."""
from alembic import op
revision='p11z_split_note_ownership'
down_revision='p11y_split_credit_note_guard'
branch_labels=depends_on=None
def upgrade():
    op.execute('''CREATE OR REPLACE FUNCTION validate_split_credit_note() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE refund record; BEGIN
      SELECT * INTO refund FROM sales WHERE id=NEW.refund_sale_id;
      IF refund.payment_method='split_refund' THEN
        IF NEW.company_id<>refund.company_id OR NOT EXISTS(SELECT FROM credit_receivables WHERE id=NEW.receivable_id AND company_id=refund.company_id AND sale_id=refund.original_sale_id) THEN RAISE EXCEPTION 'Split credit note original tenant/receivable differs'; END IF;
        IF (SELECT COALESCE(sum(amount),0) FROM credit_refund_adjustments WHERE refund_sale_id=NEW.refund_sale_id)<>
           (SELECT COALESCE(sum(amount_base),0) FROM sale_tender_refunds WHERE refund_sale_id=NEW.refund_sale_id AND kind='debt_reduction') THEN RAISE EXCEPTION 'Split credit note requires original tender debt allocation'; END IF;
      END IF; RETURN NULL; END $$''')
def downgrade():raise RuntimeError('Original tenant/receivable and every session/transaction safeguard require compatible forward recovery')
