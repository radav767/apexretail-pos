"""Fence abandoned uncommitted workflow UUIDs before allowing replacements."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p11q_workflow_cancel_fences'
down_revision='p11p_stock_movement_revisions'
branch_labels=depends_on=None

def upgrade():
    op.create_table('workflow_cancellations',s.Column('request_id',UUID(as_uuid=True),primary_key=True),
        s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),primary_key=True),
        s.Column('actor_type',s.String(10),primary_key=True),s.Column('actor_id',UUID(as_uuid=True),primary_key=True),
        s.Column('reason',s.String(500),nullable=False),s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()))
    op.execute('CREATE TRIGGER workflow_cancellation_immutable BEFORE UPDATE OR DELETE ON workflow_cancellations FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT ON workflow_cancellations TO apex_user; END IF; END $$")

def downgrade():raise RuntimeError('Late packet cancellation fences and every session/transaction safeguard must survive forward recovery')
