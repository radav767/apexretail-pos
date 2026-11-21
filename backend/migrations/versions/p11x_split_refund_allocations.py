"""Immutable debt-first split refund allocations and original currency budgets."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p11x_split_refund_allocations'
down_revision='p11w_split_snapshot_guards'
branch_labels=depends_on=None

def upgrade():
    op.create_table('sale_tender_refunds',s.Column('id',UUID(as_uuid=True),primary_key=True),s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),s.Column('refund_sale_id',UUID(as_uuid=True),s.ForeignKey('sales.id'),nullable=False),s.Column('tender_id',UUID(as_uuid=True),s.ForeignKey('sale_tenders.id'),nullable=False),s.Column('kind',s.String(24),nullable=False),s.Column('amount_base',s.Numeric(12,2),nullable=False),s.Column('amount_original',s.Numeric(18,4),nullable=False),s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()),s.UniqueConstraint('refund_sale_id','tender_id',name='uq_refund_original_tender'),s.CheckConstraint("kind IN ('debt_reduction','paid_refund') AND amount_base>0 AND amount_original>0",name='ck_split_refund_positive'))
    op.create_index('ix_split_refund_tender','sale_tender_refunds',['tender_id'])
    op.execute('CREATE TRIGGER split_refund_immutable BEFORE UPDATE OR DELETE ON sale_tender_refunds FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute('''CREATE FUNCTION validate_split_refund_budget() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE target uuid; refund record; original record; BEGIN
      IF TG_TABLE_NAME='sales' THEN target=NEW.id; ELSE target=NEW.refund_sale_id; END IF;
      SELECT * INTO refund FROM sales WHERE id=target;
      SELECT * INTO original FROM sales WHERE id=refund.original_sale_id FOR UPDATE;
      IF refund.payment_method<>'split_refund' OR original.payment_method IS DISTINCT FROM 'split' OR refund.company_id<>original.company_id OR refund.total_amount>=0 OR (SELECT COALESCE(sum(amount_base),0) FROM sale_tender_refunds WHERE refund_sale_id=target)<>-refund.total_amount THEN RAISE EXCEPTION 'Split refund sum or original differs'; END IF;
      IF EXISTS(SELECT FROM sale_tender_refunds r JOIN sale_tenders t ON t.id=r.tender_id WHERE r.refund_sale_id=target AND (r.company_id<>refund.company_id OR t.company_id<>refund.company_id OR t.sale_id<>original.id OR (r.kind='debt_reduction')<>(t.method='credit'))) THEN RAISE EXCEPTION 'Split refund original tender ownership differs'; END IF;
      IF EXISTS(SELECT FROM sale_tenders t JOIN sale_tender_refunds r ON r.tender_id=t.id WHERE t.sale_id=original.id GROUP BY t.id HAVING sum(r.amount_base)>t.applied_base OR sum(r.amount_original)>t.applied_original OR sum(r.amount_original)<>round(t.applied_original*sum(r.amount_base)/t.applied_base,t.currency_places)) THEN RAISE EXCEPTION 'Original split refund budget or cumulative currency proof differs'; END IF;
      IF (SELECT COALESCE(sum(amount_base),0) FROM sale_tender_refunds WHERE refund_sale_id=target AND kind='debt_reduction')<>(SELECT COALESCE(sum(amount),0) FROM credit_refund_adjustments WHERE refund_sale_id=target) THEN RAISE EXCEPTION 'Split credit note allocation differs'; END IF; RETURN NULL; END $$''')
    op.execute('CREATE CONSTRAINT TRIGGER split_refund_budget AFTER INSERT ON sale_tender_refunds DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_split_refund_budget()')
    op.execute("CREATE CONSTRAINT TRIGGER split_refund_sale_budget AFTER INSERT OR UPDATE ON sales DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN(NEW.payment_method='split_refund') EXECUTE FUNCTION validate_split_refund_budget()")
    op.execute('''CREATE OR REPLACE FUNCTION freeze_split_sale_terms() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.payment_method IN ('split','split_refund') AND (to_jsonb(NEW)-'reprint_count'-'last_reprinted_at'-'status') IS DISTINCT FROM (to_jsonb(OLD)-'reprint_count'-'last_reprinted_at'-'status') THEN RAISE EXCEPTION 'Original split sale/refund snapshots are immutable'; END IF; RETURN NEW; END $$''')
    op.execute('''CREATE OR REPLACE FUNCTION freeze_split_sale_items() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP IN ('UPDATE','DELETE') AND EXISTS(SELECT FROM sales WHERE id=OLD.sale_id AND payment_method IN ('split','split_refund')) THEN RAISE EXCEPTION 'Original split sale/refund items are immutable'; END IF;
      IF TG_OP<>'DELETE' AND EXISTS(SELECT FROM sales WHERE id=NEW.sale_id AND payment_method IN ('split','split_refund')) AND (EXISTS(SELECT FROM sale_tenders WHERE sale_id=NEW.sale_id) OR EXISTS(SELECT FROM sale_tender_refunds WHERE refund_sale_id=NEW.sale_id)) THEN RAISE EXCEPTION 'Original split sale/refund items cannot be extended'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute("DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT ON sale_tender_refunds TO apex_user; END IF; END $$")

def downgrade():raise RuntimeError('Original refund/currency/credit evidence and all revocation/queue safeguards require compatible forward recovery')
