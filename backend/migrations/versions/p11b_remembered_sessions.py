"""Revocable per-browser business sessions with rotating hashed refresh credentials."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11b_remembered_sessions'
down_revision = 'p11a_user_session_revocation'
branch_labels = depends_on = None


def upgrade():
    op.create_table('business_sessions',
        s.Column('id', UUID(as_uuid=True), primary_key=True),
        s.Column('user_id', UUID(as_uuid=True), s.ForeignKey('users.id'), nullable=False),
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), nullable=False),
        s.Column('session_version', s.Integer(), nullable=False),
        s.Column('remembered', s.Boolean(), nullable=False), s.Column('audience', s.String(30), nullable=False),
        s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
        s.Column('expires_at', s.DateTime(timezone=True), nullable=False), s.Column('revoked_at', s.DateTime(timezone=True)))
    op.create_index('ix_business_sessions_user_id', 'business_sessions', ['user_id'])
    op.create_index('ix_business_sessions_company_id', 'business_sessions', ['company_id'])
    op.create_table('business_refresh_credentials', s.Column('token_hash', s.String(64), primary_key=True),
        s.Column('session_id', UUID(as_uuid=True), s.ForeignKey('business_sessions.id'), nullable=False),
        s.Column('consumed_at', s.DateTime(timezone=True)), s.Column('expires_at', s.DateTime(timezone=True), nullable=False))
    op.create_index('ix_business_refresh_credentials_session_id', 'business_refresh_credentials', ['session_id'])
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
      GRANT SELECT,INSERT,UPDATE ON business_sessions,business_refresh_credentials TO apex_user;
      END IF; END $$""")


def downgrade():
    raise RuntimeError('Business session enforcement must survive rollback; use reviewed forward recovery')
