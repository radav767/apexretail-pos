"""Hashed reset grants, encrypted sink outbox and durable recovery throttles."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11c_password_recovery'
down_revision = 'p11b_remembered_sessions'
branch_labels = depends_on = None


def upgrade():
    op.create_table('business_password_resets', s.Column('token_hash', s.String(64), primary_key=True),
        s.Column('user_id', UUID(as_uuid=True), s.ForeignKey('users.id'), nullable=False),
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), nullable=False),
        s.Column('session_version', s.Integer(), nullable=False), s.Column('expires_at', s.DateTime(timezone=True), nullable=False),
        s.Column('consumed_at', s.DateTime(timezone=True)))
    op.create_index('ix_business_password_resets_user_id', 'business_password_resets', ['user_id'])
    op.create_table('business_email_outbox', s.Column('id', UUID(as_uuid=True), primary_key=True),
        s.Column('user_id', UUID(as_uuid=True), s.ForeignKey('users.id'), nullable=False),
        s.Column('company_id', UUID(as_uuid=True), s.ForeignKey('companies.id'), nullable=False),
        s.Column('ciphertext', s.LargeBinary(), nullable=False), s.Column('status', s.String(20), nullable=False),
        s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
        s.Column('sink_written_at', s.DateTime(timezone=True)))
    op.create_table('business_auth_throttles', s.Column('bucket', s.String(64), primary_key=True),
        s.Column('attempts', s.Integer(), nullable=False), s.Column('expires_at', s.DateTime(timezone=True), nullable=False))
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
      GRANT SELECT,INSERT,UPDATE ON business_password_resets,business_email_outbox,business_auth_throttles TO apex_user;
      END IF; END $$""")


def downgrade():
    raise RuntimeError('Recovery/session revocation state must survive rollback; use reviewed forward recovery')
