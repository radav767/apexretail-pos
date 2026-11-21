"""Keep private normalized document assets and output bytes immutable."""
from alembic import op
revision='p11r_private_document_assets'
down_revision='p11q_workflow_cancel_fences'
branch_labels=depends_on=None

def upgrade():
    op.execute('''CREATE OR REPLACE FUNCTION freeze_workflow_evidence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Workflow evidence cannot be deleted'; END IF;
      IF NEW.company_id IS DISTINCT FROM OLD.company_id OR NEW.branch_id IS DISTINCT FROM OLD.branch_id OR NEW.kind IS DISTINCT FROM OLD.kind
         OR NEW.version<=OLD.version OR OLD.kind IN ('template','document','document_media','document_output')
         OR OLD.kind='po' AND OLD.state<>'draft' AND NEW.payload IS DISTINCT FROM OLD.payload
      THEN RAISE EXCEPTION 'Workflow scope or frozen evidence changed'; END IF;
      RETURN NEW; END $$''')

def downgrade():raise RuntimeError('Private document evidence and every revocation/queue/transaction safeguard require forward recovery')
