"""Extend existing platform identities; no tenant backfill or financial mutation."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID

revision='p10a_platform_management'
down_revision='p9b_fiscal_protocol'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('platform_admins',s.Column('mfa_secret',s.String(500)))
    op.add_column('platform_admins',s.Column('mfa_last_step',s.Integer(),nullable=False,server_default='-1'))
    # Old password-only sessions never gain MFA assurance through migration.
    op.add_column('platform_sessions',s.Column('mfa_verified',s.Boolean(),nullable=False,server_default=s.false()))
    op.create_table('platform_challenges',s.Column('id',UUID(as_uuid=True),primary_key=True),
        s.Column('admin_id',UUID(as_uuid=True),s.ForeignKey('platform_admins.id'),nullable=False),
        s.Column('token_hash',s.String(64),nullable=False,unique=True),s.Column('pending_secret',s.String(500)),
        s.Column('expires_at',s.DateTime(timezone=True),nullable=False),s.Column('used_at',s.DateTime(timezone=True)))
    op.create_table('platform_settings',s.Column('id',s.Integer(),primary_key=True),
        s.Column('version',s.Integer(),nullable=False),s.Column('values',s.JSON(),nullable=False),
        s.CheckConstraint('id=1 AND version>0',name='ck_platform_settings_singleton'))
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT,INSERT,UPDATE ON platform_challenges,platform_settings TO apex_user;
        END IF; END $$""")


def downgrade():
    for query in ('SELECT EXISTS(SELECT FROM platform_admins WHERE mfa_secret IS NOT NULL)',
                  'SELECT EXISTS(SELECT FROM platform_challenges)', 'SELECT EXISTS(SELECT FROM platform_settings)',
                  'SELECT EXISTS(SELECT FROM platform_sessions WHERE mfa_verified)'):
        if op.get_bind().execute(s.text(query)).scalar():
            raise RuntimeError('Platform security/settings records exist; use reviewed forward recovery')
    op.drop_table('platform_settings');op.drop_table('platform_challenges')
    op.drop_column('platform_sessions','mfa_verified')
    op.drop_column('platform_admins','mfa_last_step');op.drop_column('platform_admins','mfa_secret')
