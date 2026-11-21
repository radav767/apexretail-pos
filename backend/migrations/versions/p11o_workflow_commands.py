"""Scoped procurement/count/document projections and immutable commands."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='p11o_workflow_commands'
down_revision='p11n_quotation_lifecycle'
branch_labels=depends_on=None

def upgrade():
    op.create_table('workflow_records',s.Column('id',UUID(as_uuid=True),primary_key=True),
        s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),
        s.Column('branch_id',UUID(as_uuid=True),s.ForeignKey('branches.id')),
        s.Column('kind',s.String(24),nullable=False),s.Column('state',s.String(24),nullable=False),
        s.Column('version',s.Integer,nullable=False),s.Column('payload',JSONB,nullable=False),
        s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()))
    op.create_index('ix_workflow_scope','workflow_records',['company_id','branch_id','kind'])
    op.create_table('workflow_commands',s.Column('request_id',UUID(as_uuid=True),primary_key=True),
        s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),
        s.Column('record_id',UUID(as_uuid=True),s.ForeignKey('workflow_records.id'),nullable=False),
        s.Column('kind',s.String(40),nullable=False),s.Column('actor_type',s.String(10),nullable=False),s.Column('actor_id',UUID(as_uuid=True),nullable=False),
        s.Column('device_id',UUID(as_uuid=True),s.ForeignKey('devices.id')),s.Column('assignment_revision',s.Integer),
        s.Column('payload_hash',s.String(64),nullable=False),s.Column('result',JSONB,nullable=False),
        s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()))
    op.create_index('ix_workflow_command_scope','workflow_commands',['company_id','record_id','kind'])
    op.execute('CREATE TRIGGER workflow_commands_immutable BEFORE UPDATE OR DELETE ON workflow_commands FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute('''CREATE FUNCTION freeze_workflow_evidence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Workflow evidence cannot be deleted'; END IF;
      IF NEW.company_id IS DISTINCT FROM OLD.company_id OR NEW.branch_id IS DISTINCT FROM OLD.branch_id OR NEW.kind IS DISTINCT FROM OLD.kind
         OR NEW.version<=OLD.version OR OLD.kind IN ('template','document')
         OR OLD.kind='po' AND OLD.state<>'draft' AND NEW.payload IS DISTINCT FROM OLD.payload
      THEN RAISE EXCEPTION 'Workflow scope or frozen evidence changed'; END IF;
      RETURN NEW; END $$''')
    op.execute('CREATE TRIGGER workflow_frozen BEFORE UPDATE OR DELETE ON workflow_records FOR EACH ROW EXECUTE FUNCTION freeze_workflow_evidence()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT,UPDATE ON workflow_records TO apex_user; GRANT SELECT,INSERT ON workflow_commands TO apex_user; END IF; END $$")

def downgrade():
    raise RuntimeError('Workflow stock ownership and all session/replay safeguards require compatible forward recovery')
