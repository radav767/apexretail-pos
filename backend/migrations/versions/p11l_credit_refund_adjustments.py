"""Unpaid credit notes with immutable refund linkage; preserve original debt."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision = 'p11l_credit_refund_adjustments'
down_revision = 'p11k_refund_command_receipts'
branch_labels = depends_on = None


def upgrade():
    op.add_column('credit_receivables', s.Column('amount_credited', s.Numeric(12,2), nullable=False, server_default='0'))
    op.drop_constraint('ck_receivables_balance_projection', 'credit_receivables')
    op.create_check_constraint('ck_receivables_balance_projection','credit_receivables','outstanding_balance = original_amount - amount_settled - amount_credited')
    op.create_check_constraint('ck_receivables_credited_range','credit_receivables','amount_credited >= 0 AND amount_settled + amount_credited <= original_amount')
    op.create_table('credit_refund_adjustments',
        s.Column('id',UUID(as_uuid=True),primary_key=True),
        s.Column('company_id',UUID(as_uuid=True),s.ForeignKey('companies.id'),nullable=False),
        s.Column('receivable_id',UUID(as_uuid=True),s.ForeignKey('credit_receivables.id'),nullable=False),
        s.Column('refund_sale_id',UUID(as_uuid=True),s.ForeignKey('sales.id'),nullable=False,unique=True),
        s.Column('amount',s.Numeric(12,2),nullable=False),
        s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now()),
        s.CheckConstraint('amount > 0',name='ck_credit_refund_amount_positive'))
    op.create_index('ix_credit_refund_company','credit_refund_adjustments',['company_id'])
    op.execute('CREATE TRIGGER credit_refund_immutable BEFORE UPDATE OR DELETE ON credit_refund_adjustments FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON credit_refund_adjustments TO apex_user; END IF; END $$")


def downgrade():
    raise RuntimeError('Debt notes, transaction proofs and every session revocation must survive rollback; use reviewed forward recovery')
