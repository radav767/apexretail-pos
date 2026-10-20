"""Opt-in commercial plans and separate platform administration. No backfill."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID
revision='p8a_commercial_billing'
down_revision='p7j_variant_batches'
branch_labels=None
depends_on=None
TABLES=('platform_admins','platform_sessions','platform_audit','billing_plans','billing_invoices','billing_payments','billing_notices')
def u(name,target=None,**kw):return s.Column(name,UUID(as_uuid=True),*([s.ForeignKey(target)] if target else []),**kw)
def stamp():return s.Column('created_at',s.DateTime(timezone=True),nullable=False,server_default=s.func.now())

def upgrade():
    op.add_column('company_subscriptions',s.Column('commercial_terms',s.JSON(),nullable=True))
    op.create_table('platform_admins',u('id',primary_key=True),s.Column('email',s.String(160),nullable=False,unique=True),
        s.Column('password_hash',s.String(160),nullable=False),s.Column('role',s.String(20),nullable=False),
        s.Column('active',s.Boolean(),nullable=False),s.Column('failed_attempts',s.Integer(),nullable=False),s.Column('locked_until',s.DateTime(timezone=True)),
        s.CheckConstraint("role IN ('super_admin','billing','support')",name='ck_platform_role'))
    op.create_table('platform_sessions',u('id',primary_key=True),u('admin_id','platform_admins.id',nullable=False),
        s.Column('token_hash',s.String(64),nullable=False,unique=True),s.Column('expires_at',s.DateTime(timezone=True),nullable=False),s.Column('revoked_at',s.DateTime(timezone=True)))
    op.create_table('platform_audit',u('id',primary_key=True),u('admin_id','platform_admins.id'),u('company_id','companies.id'),
        s.Column('action',s.String(80),nullable=False),s.Column('details',s.JSON(),nullable=False),stamp())
    op.create_table('billing_plans',u('id',primary_key=True),s.Column('name',s.String(80),nullable=False),
        s.Column('version',s.Integer(),nullable=False),s.Column('active',s.Boolean(),nullable=False),s.Column('terms',s.JSON(),nullable=False))
    op.create_table('billing_invoices',u('id',primary_key=True),u('company_id','companies.id',nullable=False),u('request_id',nullable=False),
        s.Column('payload_hash',s.String(64),nullable=False),u('plan_id','billing_plans.id',nullable=False),s.Column('snapshot',s.JSON(),nullable=False),
        s.Column('amount',s.Numeric(18,4),nullable=False),s.Column('currency',s.String(8),nullable=False),s.Column('decimal_places',s.Integer(),nullable=False),
        s.Column('due_at',s.DateTime(timezone=True),nullable=False),s.Column('fulfilled_at',s.DateTime(timezone=True)),stamp(),
        s.UniqueConstraint('company_id','request_id',name='uq_billing_invoice_request'),s.CheckConstraint('amount > 0 AND decimal_places BETWEEN 0 AND 4',name='ck_billing_invoice_amount'))
    op.create_table('billing_payments',u('id',primary_key=True),u('company_id','companies.id',nullable=False),u('invoice_id','billing_invoices.id',nullable=False),
        u('request_id',nullable=False),u('admin_id','platform_admins.id',nullable=False),s.Column('amount',s.Numeric(18,4),nullable=False),
        s.Column('method',s.String(20),nullable=False),s.Column('reference',s.String(160),nullable=False),stamp(),
        s.UniqueConstraint('company_id','request_id',name='uq_billing_payment_request'),s.UniqueConstraint('company_id','reference',name='uq_billing_payment_reference'),
        s.CheckConstraint('amount > 0',name='ck_billing_payment_amount'))
    op.create_table('billing_notices',u('id',primary_key=True),u('company_id','companies.id',nullable=False),
        s.Column('event_key',s.String(200),nullable=False,unique=True),s.Column('kind',s.String(40),nullable=False),s.Column('message',s.String(500),nullable=False),stamp())
    for table,columns in [('billing_invoices',['company_id']),('billing_payments',['company_id']),('billing_payments',['invoice_id']),('billing_notices',['company_id'])]:
        op.create_index('ix_'+table+'_'+'_'.join(columns),table,columns)
    op.execute("""CREATE FUNCTION reject_commercial_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Commercial ledger is append-only'; END $$""")
    for table in ('billing_payments','platform_audit','billing_notices'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_commercial_mutation()')
    op.execute("""CREATE FUNCTION protect_billing_invoice() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Invoice cannot be deleted'; END IF;
        IF OLD.fulfilled_at IS NOT NULL OR NEW.fulfilled_at IS NULL OR
           (to_jsonb(NEW)-'fulfilled_at') IS DISTINCT FROM (to_jsonb(OLD)-'fulfilled_at') THEN
        RAISE EXCEPTION 'Invoice snapshot is immutable'; END IF; RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER billing_invoice_immutable BEFORE UPDATE OR DELETE ON billing_invoices FOR EACH ROW EXECUTE FUNCTION protect_billing_invoice()')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT,INSERT,UPDATE ON platform_admins,platform_sessions,billing_plans TO apex_user;
        GRANT SELECT,INSERT ON platform_audit,billing_invoices,billing_payments,billing_notices TO apex_user;
        GRANT UPDATE(fulfilled_at) ON billing_invoices TO apex_user;
        GRANT UPDATE(commercial_terms) ON company_subscriptions TO apex_user;
    END IF; END $$""")

def downgrade():
    bind=op.get_bind()
    for table in TABLES:
        if bind.execute(s.text(f'SELECT EXISTS(SELECT FROM {table})')).scalar():raise RuntimeError('Commercial data exists; use forward recovery')
    if bind.execute(s.text('SELECT EXISTS(SELECT FROM company_subscriptions WHERE commercial_terms IS NOT NULL)')).scalar():raise RuntimeError('Commercial terms exist; use forward recovery')
    for table in reversed(TABLES):op.drop_table(table)
    op.execute('DROP FUNCTION protect_billing_invoice()')
    op.execute('DROP FUNCTION reject_commercial_mutation()')
    op.drop_column('company_subscriptions','commercial_terms')
