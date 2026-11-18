"""Single-use, account/branch/role/version-bound Backoffice handoff grants."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11d_backoffice_handoff'
down_revision = 'p11c_password_recovery'
branch_labels = depends_on = None


def upgrade():
    op.create_table('business_backoffice_handoffs', s.Column('token_hash', s.String(64), primary_key=True),
        s.Column('user_id', UUID(as_uuid=True), s.ForeignKey('users.id'), nullable=False),
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), nullable=False),
        s.Column('branch_id', UUID(as_uuid=True), s.ForeignKey('branches.id'), nullable=False),
        s.Column('source_session_id', UUID(as_uuid=True), s.ForeignKey('business_sessions.id')),
        s.Column('session_version', s.Integer(), nullable=False), s.Column('role', s.String(40), nullable=False),
        s.Column('audience', s.String(30), nullable=False), s.Column('receiver_hash', s.String(64)),
        s.Column('expires_at', s.DateTime(timezone=True), nullable=False), s.Column('consumed_at', s.DateTime(timezone=True)))
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
      GRANT SELECT,INSERT,UPDATE ON business_backoffice_handoffs TO apex_user;
      END IF; END $$""")


def downgrade():
    raise RuntimeError('Handoff/session enforcement must survive rollback; use reviewed forward recovery')
