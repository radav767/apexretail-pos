"""Immutable versioned split sale allocations; no provider/offline enablement."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p11v_split_tender_evidence'
down_revision='p11u_quotation_revision_chain'
branch_labels=depends_on=None

def upgrade():
    op.create_table('sale_tenders',s.Column('id',UUID(as_uuid=True),primary_key=True),s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),s.Column('sale_id',UUID(as_uuid=True),s.ForeignKey('sales.id'),nullable=False),s.Column('method',s.String(16),nullable=False),s.Column('currency_code',s.String(8),nullable=False),s.Column('currency_places',s.Integer,nullable=False),s.Column('applied_original',s.Numeric(18,4),nullable=False),s.Column('tendered_original',s.Numeric(18,4),nullable=False),s.Column('change_original',s.Numeric(18,4),nullable=False),s.Column('applied_base',s.Numeric(12,2),nullable=False),s.Column('exchange_rate_id',UUID(as_uuid=True),s.ForeignKey('currency_exchange_rates.id')),s.Column('exchange_rate_snapshot',s.Numeric(20,10),nullable=False),s.Column('currency_config_version',s.Integer,nullable=False),s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()),s.CheckConstraint("method IN ('cash','credit') AND applied_original>0 AND applied_base>0 AND exchange_rate_snapshot>0 AND currency_places BETWEEN 0 AND 4 AND currency_config_version>=1",name='ck_sale_tender_positive'),s.CheckConstraint("(method='cash' AND tendered_original>=applied_original AND change_original=tendered_original-applied_original) OR (method='credit' AND tendered_original=0 AND change_original=0)",name='ck_sale_tender_cash_change'))
    op.create_index('ix_sale_tender_scope','sale_tenders',['company_id','sale_id'])
    op.execute('CREATE TRIGGER sale_tender_immutable BEFORE UPDATE OR DELETE ON sale_tenders FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute('''CREATE FUNCTION validate_split_tender_sum() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE target uuid; current_sale record; n integer; allocated numeric; credit_total numeric; BEGIN
      IF TG_TABLE_NAME='sales' THEN target=NEW.id; ELSE target=NEW.sale_id; END IF; SELECT * INTO current_sale FROM sales WHERE id=target;
      SELECT count(*),COALESCE(sum(applied_base),0) INTO n,allocated FROM sale_tenders WHERE sale_id=target;
      IF current_sale.payment_method<>'split' OR n<2 OR n>20 OR allocated<>current_sale.total_amount OR EXISTS(SELECT FROM sale_tenders WHERE sale_id=target AND company_id<>current_sale.company_id) THEN
        RAISE EXCEPTION 'Split tender ownership or total differs'; END IF;
      IF (SELECT count(*) FROM sale_tenders WHERE sale_id=target AND method='credit')>1 OR NOT EXISTS(SELECT FROM sale_tenders WHERE sale_id=target AND method='cash') THEN RAISE EXCEPTION 'Split method budget differs'; END IF;
      SELECT COALESCE(sum(applied_base),0) INTO credit_total FROM sale_tenders WHERE sale_id=target AND method='credit';
      IF EXISTS(SELECT FROM sale_tenders WHERE sale_id=target AND method='credit' AND (currency_code<>current_sale.base_currency_code OR exchange_rate_snapshot<>1 OR exchange_rate_id IS NOT NULL OR applied_original<>applied_base)) THEN RAISE EXCEPTION 'Credit tender must use original base currency'; END IF;
      IF credit_total>0 AND NOT EXISTS(SELECT FROM credit_receivables WHERE sale_id=target AND company_id=current_sale.company_id AND original_amount=credit_total) OR credit_total=0 AND EXISTS(SELECT FROM credit_receivables WHERE sale_id=target) THEN RAISE EXCEPTION 'Split credit projection differs'; END IF; RETURN NULL; END $$''')
    op.execute('CREATE CONSTRAINT TRIGGER split_tender_total AFTER INSERT ON sale_tenders DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_split_tender_sum()')
    op.execute("CREATE CONSTRAINT TRIGGER split_sale_total AFTER INSERT OR UPDATE ON sales DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN(NEW.payment_method='split') EXECUTE FUNCTION validate_split_tender_sum()")
    op.execute('''CREATE FUNCTION freeze_split_sale_terms() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.payment_method='split' AND (NEW.company_id,NEW.branch_id,NEW.customer_id,NEW.device_id,NEW.base_currency_code,NEW.total_amount,NEW.subtotal_amount,NEW.tax_amount,NEW.discount_amount,NEW.amount_received,NEW.change_due,NEW.payment_method) IS DISTINCT FROM (OLD.company_id,OLD.branch_id,OLD.customer_id,OLD.device_id,OLD.base_currency_code,OLD.total_amount,OLD.subtotal_amount,OLD.tax_amount,OLD.discount_amount,OLD.amount_received,OLD.change_due,OLD.payment_method) THEN RAISE EXCEPTION 'Original split sale terms are immutable'; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER split_sale_terms_frozen BEFORE UPDATE ON sales FOR EACH ROW EXECUTE FUNCTION freeze_split_sale_terms()')
    op.execute("DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT ON sale_tenders TO apex_user; END IF; END $$")

def downgrade():raise RuntimeError('Original tender allocations and every revocation/queue/transaction safeguard require compatible forward recovery')
