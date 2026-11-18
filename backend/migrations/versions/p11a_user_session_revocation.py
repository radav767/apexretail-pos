"""Add business user revocation version; preserve existing tokens at version zero."""
from alembic import op
import sqlalchemy as s

revision = 'p11a_user_session_revocation'
down_revision = 'p10a_platform_management'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', s.Column('session_version', s.Integer(), nullable=False, server_default='0'))
    op.create_check_constraint('ck_users_session_version', 'users', 'session_version >= 0')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT UPDATE(session_version) ON users TO apex_user;
        END IF; END $$""")


def downgrade():
    if op.get_bind().execute(s.text('SELECT EXISTS(SELECT FROM users WHERE session_version > 0)')).scalar():
        raise RuntimeError('Revoked user sessions exist; use reviewed forward recovery')
    op.drop_constraint('ck_users_session_version', 'users', type_='check')
    op.drop_column('users', 'session_version')
