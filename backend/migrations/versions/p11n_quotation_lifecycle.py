"""Quotation validity, frozen terms and immutable workflow command proof."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='p11n_quotation_lifecycle'
down_revision='p11m_checkout_customer_commands'
branch_labels=depends_on=None


def upgrade():
    op.add_column('commerce_orders',s.Column('quotation_status',s.String(20)))
    op.add_column('commerce_orders',s.Column('quotation_valid_until',s.DateTime(timezone=True)))
    op.add_column('commerce_orders',s.Column('quotation_terms',JSONB))
    op.create_check_constraint('ck_quotation_status','commerce_orders',"quotation_status IS NULL OR quotation_status IN ('draft','sent','accepted','rejected')")
    op.create_table('quotation_commands',
        s.Column('request_id',UUID(as_uuid=True),primary_key=True),s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),
        s.Column('order_id',UUID(as_uuid=True),s.ForeignKey('commerce_orders.id'),nullable=False),
        s.Column('actor_type',s.String(10),nullable=False),s.Column('actor_id',UUID(as_uuid=True),nullable=False),s.Column('payload_hash',s.String(64),nullable=False),
        s.Column('device_id',UUID(as_uuid=True),s.ForeignKey('devices.id'),nullable=False),s.Column('assignment_revision',s.Integer,nullable=False),
        s.Column('action',s.String(20),nullable=False),s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()))
    op.create_index('ix_quotation_commands_company','quotation_commands',['company_id'])
    op.execute('CREATE TRIGGER quotation_commands_immutable BEFORE UPDATE OR DELETE ON quotation_commands FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute('''CREATE FUNCTION freeze_quotation_terms() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.quotation_terms IS NOT NULL AND
        (NEW.quotation_terms IS DISTINCT FROM OLD.quotation_terms OR NEW.quotation_valid_until IS DISTINCT FROM OLD.quotation_valid_until
         OR NEW.company_id IS DISTINCT FROM OLD.company_id OR NEW.branch_id IS DISTINCT FROM OLD.branch_id
         OR NEW.device_id IS DISTINCT FROM OLD.device_id OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
         OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.quotation_status='draft'
         OR OLD.quotation_status IN ('accepted','rejected') AND NEW.quotation_status IS DISTINCT FROM OLD.quotation_status)
      THEN RAISE EXCEPTION 'Quotation terms are frozen'; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER quotation_terms_frozen BEFORE UPDATE ON commerce_orders FOR EACH ROW EXECUTE FUNCTION freeze_quotation_terms()')
    op.execute('''CREATE FUNCTION freeze_quotation_items() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE target uuid; BEGIN
      IF TG_OP='DELETE' THEN target=OLD.order_id; ELSE target=NEW.order_id; END IF;
      IF EXISTS(SELECT FROM commerce_orders WHERE id=target AND quotation_terms IS NOT NULL)
         OR TG_OP='UPDATE' AND EXISTS(SELECT FROM commerce_orders WHERE id=OLD.order_id AND quotation_terms IS NOT NULL)
      THEN RAISE EXCEPTION 'Quotation items are frozen'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER quotation_items_frozen BEFORE INSERT OR UPDATE OR DELETE ON commerce_order_items FOR EACH ROW EXECUTE FUNCTION freeze_quotation_items()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON quotation_commands TO apex_user; END IF; END $$")


def downgrade():
    raise RuntimeError('Frozen quotation authority and every session/transaction safeguard must survive compatible forward recovery')
