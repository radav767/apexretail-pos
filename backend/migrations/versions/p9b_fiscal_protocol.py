"""Additive fiscal test protocol state and immutable evidence; never activates FDMS."""
from alembic import op
import sqlalchemy as s
from sqlalchemy.dialects.postgresql import UUID

revision = 'p9b_fiscal_protocol'
down_revision = 'p9a_fiscal_preparation'
branch_labels = None
depends_on = None


def uid(name, target=None, **kw):
    return s.Column(name, UUID(as_uuid=True), *([s.ForeignKey(target)] if target else []), **kw)


def upgrade():
    op.create_table('fiscal_protocol_states', uid('company_id', 'companies.id', primary_key=True),
                    s.Column('data', s.JSON(), nullable=False))
    op.create_table('fiscal_documents', uid('id', primary_key=True), uid('company_id', 'companies.id', nullable=False),
                    uid('preparation_id', 'fiscal_preparations.id', nullable=False),
                    s.Column('day_no', s.Integer(), nullable=False), s.Column('global_no', s.Integer(), nullable=False),
                    s.Column('payload', s.JSON(), nullable=False), s.Column('payload_hash', s.String(64), nullable=False),
                    s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
                    s.UniqueConstraint('company_id', 'preparation_id', name='uq_fiscal_document_preparation'),
                    s.UniqueConstraint('company_id', 'global_no', name='uq_fiscal_document_global'),
                    s.CheckConstraint('day_no > 0 AND global_no > 0', name='ck_fiscal_document_number'))
    op.create_table('fiscal_protocol_events', uid('id', primary_key=True), uid('company_id', 'companies.id', nullable=False),
                    uid('document_id', 'fiscal_documents.id'), s.Column('sequence', s.BigInteger(), nullable=False),
                    s.Column('kind', s.String(50), nullable=False), s.Column('details', s.JSON(), nullable=False),
                    s.Column('created_at', s.DateTime(timezone=True), nullable=False, server_default=s.func.now()),
                    s.UniqueConstraint('company_id', 'sequence', name='uq_fiscal_event_sequence'))
    for table in ('fiscal_documents', 'fiscal_protocol_events'):
        op.create_index(f'ix_{table}_company_id', table, ['company_id'])
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_fiscal_records()')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT, INSERT, UPDATE ON fiscal_protocol_states TO apex_user;
        GRANT SELECT, INSERT ON fiscal_documents, fiscal_protocol_events TO apex_user;
        END IF; END $$""")


def downgrade():
    for table in ('fiscal_protocol_states', 'fiscal_documents', 'fiscal_protocol_events'):
        if op.get_bind().execute(s.text(f'SELECT EXISTS(SELECT FROM {table})')).scalar():
            raise RuntimeError('Fiscal protocol evidence exists; use reviewed forward recovery')
    for table in ('fiscal_protocol_events', 'fiscal_documents', 'fiscal_protocol_states'):
        op.drop_table(table)
