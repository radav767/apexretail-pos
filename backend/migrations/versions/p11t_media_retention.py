"""One mutable retention projection with immutable original command evidence."""
from alembic import op
revision='p11t_media_retention'
down_revision='p11s_document_sink_evidence'
branch_labels=depends_on=None

def upgrade():
    op.execute("CREATE UNIQUE INDEX workflow_media_retention_unique ON workflow_records(company_id,(payload->>'media_id')) WHERE kind='media_retention'")
    op.execute('''CREATE FUNCTION freeze_media_retention_scope() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.kind='media_retention' AND NEW.payload->>'media_id' IS DISTINCT FROM OLD.payload->>'media_id' THEN
        RAISE EXCEPTION 'Retention cannot be rebound to another asset'; END IF;
      RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER media_retention_scope BEFORE UPDATE ON workflow_records FOR EACH ROW EXECUTE FUNCTION freeze_media_retention_scope()')

def downgrade():raise RuntimeError('Retention/immutable evidence and every revocation/queue safeguard require forward recovery')
