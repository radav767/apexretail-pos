"""Immutable identified basic checkout customer creation, without credit grants."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p11m_checkout_customer_commands'
down_revision='p11l_credit_refund_adjustments'
branch_labels=depends_on=None


def upgrade():
    op.create_table('checkout_customer_commands',
        s.Column('request_id',UUID(as_uuid=True),primary_key=True),
        s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),
        s.Column('customer_id',UUID(as_uuid=True),s.ForeignKey('customers.id'),nullable=False,unique=True),
        s.Column('actor_type',s.String(10),nullable=False),s.Column('actor_id',UUID(as_uuid=True),nullable=False),
        s.Column('payload_hash',s.String(64),nullable=False),
        s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()))
    op.create_index('ix_checkout_customer_company','checkout_customer_commands',['company_id'])
    op.execute('CREATE TRIGGER checkout_customer_immutable BEFORE UPDATE OR DELETE ON checkout_customer_commands FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON checkout_customer_commands TO apex_user; END IF; END $$")


def downgrade():
    raise RuntimeError('Customer command proofs and every identity/revocation safeguard must survive compatible forward recovery')
