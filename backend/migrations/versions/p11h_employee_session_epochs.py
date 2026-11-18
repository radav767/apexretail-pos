"""Persistent employee revocation covers opaque sessions and legacy JWTs."""
from alembic import op
import sqlalchemy as s
revision = 'p11h_employee_session_epochs'
down_revision = 'p11g_financial_command_proofs'
branch_labels = depends_on = None


def upgrade():
    for table in ('employees', 'pos_sessions'):
        op.add_column(table, s.Column('session_version', s.Integer, nullable=False, server_default='0'))
        op.create_check_constraint('ck_'+table+'_session_version', table, 'session_version >= 0')


def downgrade():
    raise RuntimeError('Employee and user session revocation must survive rollback; use reviewed forward recovery')
