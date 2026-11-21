"""Immutable quotation revision lineage with at most one converted sale."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p11u_quotation_revision_chain'
down_revision='p11t_media_retention'
branch_labels=depends_on=None

def upgrade():
    op.add_column('commerce_orders',s.Column('quotation_root_id',UUID(as_uuid=True),s.ForeignKey('commerce_orders.id')))
    op.add_column('commerce_orders',s.Column('quotation_revision',s.Integer,nullable=False,server_default='0'))
    op.add_column('quotation_commands',s.Column('revised_order_id',UUID(as_uuid=True),s.ForeignKey('commerce_orders.id')))
    op.execute("CREATE UNIQUE INDEX quotation_revision_number ON commerce_orders(company_id,quotation_root_id,quotation_revision) WHERE quotation_root_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX quotation_lineage_conversion ON commerce_orders(company_id,(COALESCE(quotation_root_id,id))) WHERE kind='quotation' AND sale_id IS NOT NULL")
    op.execute('''CREATE FUNCTION freeze_quotation_lineage() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE p record; BEGIN
      IF TG_OP='UPDATE' AND (NEW.quotation_root_id,NEW.quotation_revision,NEW.parent_id) IS DISTINCT FROM (OLD.quotation_root_id,OLD.quotation_revision,OLD.parent_id) AND OLD.kind='quotation' THEN
        RAISE EXCEPTION 'Quotation lineage is immutable'; END IF;
      IF NEW.quotation_root_id IS NOT NULL THEN
        SELECT * INTO p FROM commerce_orders WHERE id=NEW.parent_id;
        IF NEW.kind<>'quotation' OR NEW.quotation_revision<1 OR p.id IS NULL OR p.kind<>'quotation' OR p.company_id<>NEW.company_id
           OR COALESCE(p.quotation_root_id,p.id)<>NEW.quotation_root_id OR p.quotation_terms IS NULL THEN
          RAISE EXCEPTION 'Quotation revision scope differs'; END IF;
      ELSIF NEW.quotation_revision<>0 THEN RAISE EXCEPTION 'Quotation root revision must be zero'; END IF;
      RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER quotation_lineage_frozen BEFORE INSERT OR UPDATE ON commerce_orders FOR EACH ROW EXECUTE FUNCTION freeze_quotation_lineage()')

def downgrade():raise RuntimeError('Quotation lineage and every revocation/transaction/document safeguard require compatible forward recovery')
