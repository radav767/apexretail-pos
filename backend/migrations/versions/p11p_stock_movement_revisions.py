"""DB cutoffs include net-zero moves, variant/lot/hold and scope changes."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p11p_stock_movement_revisions'
down_revision='p11o_workflow_commands'
branch_labels=depends_on=None

def upgrade():
    op.create_table('stock_revisions',s.Column('company_id',UUID(as_uuid=True),primary_key=True),s.Column('branch_id',UUID(as_uuid=True),primary_key=True),s.Column('product_id',UUID(as_uuid=True),primary_key=True),s.Column('revision',s.BigInteger,nullable=False,server_default='0'))
    op.execute('''CREATE FUNCTION bump_stock_revision(c uuid,b uuid,p uuid) RETURNS void LANGUAGE plpgsql AS $$ BEGIN
      IF c IS NULL OR b IS NULL OR p IS NULL THEN RETURN; END IF;
      INSERT INTO stock_revisions VALUES(c,b,p,1) ON CONFLICT(company_id,branch_id,product_id) DO UPDATE SET revision=stock_revisions.revision+1;
    END $$''')
    op.execute('''CREATE FUNCTION track_stock_revision() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE n jsonb; o jsonb; BEGIN
      IF TG_OP<>'DELETE' THEN n=to_jsonb(NEW); END IF;
      IF TG_OP<>'INSERT' THEN o=to_jsonb(OLD); END IF;
      IF TG_OP='UPDATE' AND TG_TABLE_NAME<>'inventory_movements' AND
         (n->'quantity',n->'active',n->'deleted',n->'branch_id',n->'product_id',n->'variant_id',n->'expires_on',n->'code') IS NOT DISTINCT FROM
         (o->'quantity',o->'active',o->'deleted',o->'branch_id',o->'product_id',o->'variant_id',o->'expires_on',o->'code') THEN RETURN NEW; END IF;
      IF TG_OP<>'DELETE' THEN PERFORM bump_stock_revision((n->>'company_id')::uuid,(n->>'branch_id')::uuid,(n->>'product_id')::uuid); END IF;
      IF TG_OP='DELETE' OR TG_OP='UPDATE' AND (n->>'branch_id',n->>'product_id') IS DISTINCT FROM (o->>'branch_id',o->>'product_id') THEN
        PERFORM bump_stock_revision((o->>'company_id')::uuid,(o->>'branch_id')::uuid,(o->>'product_id')::uuid); END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$''')
    for table in ('inventory_balances','variant_inventory_balances','product_batches','batch_return_holds','inventory_movements'):
        op.execute(f'CREATE TRIGGER stock_revision_capture AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION track_stock_revision()')
    op.execute('''CREATE FUNCTION track_inspection_revision() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE h record; BEGIN
      SELECT * INTO h FROM batch_return_holds WHERE id=NEW.hold_id;
      PERFORM bump_stock_revision(h.company_id,h.branch_id,h.product_id); RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER stock_inspection_revision AFTER INSERT ON batch_return_inspections FOR EACH ROW EXECUTE FUNCTION track_inspection_revision()')
    op.execute('''CREATE FUNCTION track_product_scope_revision() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE r record; BEGIN
      IF (NEW.category_id,NEW.track_inventory,NEW.product_type,NEW.deleted) IS DISTINCT FROM (OLD.category_id,OLD.track_inventory,OLD.product_type,OLD.deleted) THEN
        FOR r IN SELECT DISTINCT branch_id FROM stock_revisions WHERE company_id=NEW.company_id AND product_id=NEW.id LOOP
          PERFORM bump_stock_revision(NEW.company_id,r.branch_id,NEW.id); END LOOP;
      END IF; RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER stock_scope_revision AFTER UPDATE ON products FOR EACH ROW EXECUTE FUNCTION track_product_scope_revision()')
    for table in ('inventory_balances','variant_inventory_balances','product_batches','batch_return_holds'):
        op.execute(f'''INSERT INTO stock_revisions SELECT DISTINCT company_id,branch_id,product_id,0 FROM {table} WHERE branch_id IS NOT NULL ON CONFLICT DO NOTHING''')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT,UPDATE ON stock_revisions TO apex_user; END IF; END $$")

def downgrade():raise RuntimeError('Movement cutoffs and every identity/transaction proof must survive compatible forward recovery')
