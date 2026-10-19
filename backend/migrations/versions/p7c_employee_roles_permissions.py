"""advanced employees, roles and manager authorizations

Revision ID: p7c_employee_roles_permissions
Revises: p7b_variant_pricing_tax
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p7c_employee_roles_permissions"
down_revision = "p7b_variant_pricing_tax"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employee_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(240)),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "name", name="uq_employee_roles_company_name"),
    )
    op.create_index("ix_employee_roles_company_id", "employee_roles", ["company_id"])
    op.add_column("employees", sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("employees", sa.Column("role_overrides", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("employees", sa.Column("device_restricted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key("fk_employees_role_id", "employees", "employee_roles", ["role_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_employees_role_id", "employees", ["role_id"])
    op.create_table(
        "employee_device_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("employee_id", "device_id", name="uq_employee_device_access"),
    )
    for column in ("company_id", "employee_id", "device_id"):
        op.create_index(f"ix_employee_device_access_{column}", "employee_device_access", [column])
    op.create_table(
        "manager_authorizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approver_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("context_hash", sa.String(64)),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_manager_authorizations_token_hash"),
    )
    for column in ("company_id", "action", "token_hash"):
        op.create_index(f"ix_manager_authorizations_{column}", "manager_authorizations", [column])
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT,UPDATE,DELETE ON employee_roles,employee_device_access,manager_authorizations TO apex_user; END IF; END $$")
    # Existing authorized terminal deletion uses FK ON DELETE SET NULL.
    # Permit only that nested referential action, retaining every audit
    # payload/value. Direct UPDATE/DELETE still fails, including for the owner.
    op.execute("""CREATE FUNCTION prevent_audit_event_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'UPDATE' AND pg_trigger_depth() > 1
        AND (to_jsonb(NEW) - ARRAY['device_id','actor_employee_id','actor_user_id'])
          = (to_jsonb(OLD) - ARRAY['device_id','actor_employee_id','actor_user_id'])
        AND (NEW.device_id IS NOT DISTINCT FROM OLD.device_id OR NEW.device_id IS NULL)
        AND (NEW.actor_employee_id IS NOT DISTINCT FROM OLD.actor_employee_id OR NEW.actor_employee_id IS NULL)
        AND (NEW.actor_user_id IS NOT DISTINCT FROM OLD.actor_user_id OR NEW.actor_user_id IS NULL)
      THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'audit events are append-only';
    END $$""")
    op.execute("CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation()")


def downgrade():
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION prevent_audit_event_mutation()")
    op.drop_table("manager_authorizations")
    op.drop_table("employee_device_access")
    op.drop_index("ix_employees_role_id", table_name="employees")
    op.drop_constraint("fk_employees_role_id", "employees", type_="foreignkey")
    op.drop_column("employees", "device_restricted")
    op.drop_column("employees", "role_id")
    op.drop_column("employees", "role_overrides")
    op.drop_table("employee_roles")
