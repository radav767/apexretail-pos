"""Add optional business operations without rewriting historical financial records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "p7e_business_orders_batches"
down_revision = "p7d_printers_kitchen_jobs"
branch_labels = None
depends_on = None


def uid(name, target=None, **kwargs):
    return sa.Column(name, UUID(), *([sa.ForeignKey(target)] if target else []), **kwargs)


def upgrade():
    op.create_table("business_profiles", uid("company_id", "companies.id", primary_key=True),
        sa.Column("profile", sa.String(24), nullable=False), uid("tip_product_id", "products.id"), uid("service_product_id", "products.id"))
    op.create_table("dining_tables", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False), uid("branch_id", "branches.id", nullable=False),
        sa.Column("name", sa.String(60), nullable=False), sa.Column("floor", sa.String(60), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False), sa.Column("x", sa.Integer(), nullable=False), sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("branch_id", "name", name="uq_dining_table_name"),
        sa.CheckConstraint("seats > 0 AND x >= 0 AND y >= 0", name="ck_dining_table_layout"))
    op.create_table("hospitality_rooms", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False), uid("branch_id", "branches.id", nullable=False),
        sa.Column("name", sa.String(60), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("branch_id", "name", name="uq_hospitality_room_name"))
    op.create_table("guest_accounts", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False), uid("branch_id", "branches.id", nullable=False),
        uid("room_id", "hospitality_rooms.id", nullable=False), uid("customer_id", "customers.id", nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("uq_guest_room_active", "guest_accounts", ["room_id"], unique=True, postgresql_where=sa.text("active"))
    op.create_table("commerce_orders", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False), uid("branch_id", "branches.id", nullable=False),
        uid("device_id", "devices.id", nullable=False), uid("waiter_id", "employees.id"), uid("table_id", "dining_tables.id"), uid("guest_id", "guest_accounts.id"),
        uid("customer_id", "customers.id"), uid("parent_id", "commerce_orders.id"), uid("sale_id", "sales.id", unique=True),
        sa.Column("kind", sa.String(24), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        uid("request_id", nullable=False), sa.Column("number", sa.String(40), nullable=False, unique=True), sa.Column("last_dispatch_context", JSONB()),
        sa.Column("notes", sa.String(500), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "request_id", name="uq_commerce_order_request"),
        sa.CheckConstraint("status IN ('open','settled','cancelled','merged')", name="ck_commerce_order_status"))
    op.create_index("ix_commerce_orders_company_id", "commerce_orders", ["company_id"])
    op.create_table("commerce_order_items", uid("id", primary_key=True), uid("order_id", "commerce_orders.id", nullable=False), uid("product_id", "products.id", nullable=False),
        uid("variant_id", "product_variants.id"), uid("category_id"), sa.Column("name", sa.String(280), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.Column("sent_quantity", sa.Numeric(12, 3), nullable=False), sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False), sa.Column("notes", sa.String(500), nullable=False), sa.CheckConstraint("quantity >= 0 AND sent_quantity >= 0", name="ck_order_item_quantities"))
    op.create_index("ix_commerce_order_items_order_id", "commerce_order_items", ["order_id"])
    op.add_column("print_jobs", uid("order_id"))
    op.create_foreign_key("fk_print_job_order", "print_jobs", "commerce_orders", ["order_id"], ["id"], ondelete="RESTRICT")
    op.create_table("kitchen_tickets", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False), uid("order_id", "commerce_orders.id", nullable=False),
        uid("station_id", "printer_stations.id", nullable=False), uid("print_job_id", "print_jobs.id", nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "station_id", "version", name="uq_kitchen_ticket_revision"))
    op.create_table("product_batches", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False), uid("branch_id", "branches.id", nullable=False),
        uid("product_id", "products.id", nullable=False), sa.Column("code", sa.String(80), nullable=False), sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.UniqueConstraint("company_id", "branch_id", "product_id", "code", name="uq_product_batch"),
        sa.CheckConstraint("quantity >= 0", name="ck_batch_nonnegative"))
    op.create_table("batch_allocations", uid("id", primary_key=True), uid("batch_id", "product_batches.id", nullable=False),
        uid("movement_id", "inventory_movements.id", nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.UniqueConstraint("movement_id", "batch_id", name="uq_batch_movement_allocation"))
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='apex_user') THEN
      GRANT SELECT,INSERT,UPDATE ON business_profiles,dining_tables,hospitality_rooms,guest_accounts,commerce_orders,commerce_order_items,product_batches TO apex_user;
      GRANT SELECT,INSERT ON kitchen_tickets,batch_allocations TO apex_user;
      GRANT UPDATE(status) ON kitchen_tickets TO apex_user;
    END IF; END $$""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM commerce_orders) OR EXISTS(SELECT 1 FROM product_batches) OR EXISTS(SELECT 1 FROM guest_accounts) OR EXISTS(SELECT 1 FROM business_profiles) OR EXISTS(SELECT 1 FROM dining_tables) OR EXISTS(SELECT 1 FROM hospitality_rooms)")).scalar():
        raise RuntimeError("Phase 7D operational records exist. Archive/review them or use forward recovery; refusing destructive downgrade")
    for table in ("batch_allocations", "product_batches", "kitchen_tickets"):
        op.drop_table(table)
    op.drop_constraint("fk_print_job_order", "print_jobs", type_="foreignkey")
    op.drop_column("print_jobs", "order_id")
    for table in ("commerce_order_items", "commerce_orders", "guest_accounts", "hospitality_rooms", "dining_tables", "business_profiles"):
        op.drop_table(table)
