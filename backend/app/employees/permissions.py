"""Canonical employee permissions and backwards-compatible role presets."""

from collections.abc import Mapping


PERMISSION_GROUPS: dict[str, dict[str, str]] = {
    "business_operations": {
        "restaurant_manage": "Manage restaurant tables and bills",
        "orders_manage": "Create and edit own open orders",
        "orders_send": "Send kitchen and bar tickets",
        "orders_settle": "Settle restaurant bills",
        "kitchen_view": "View kitchen tickets",
        "kitchen_update": "Update kitchen ticket status",
        "bar_view": "View bar tickets",
        "bar_update": "Update bar ticket status",
        "hospitality_manage": "Manage rooms and guest accounts",
        "batches_manage": "Manage product batches",
        "batches_view": "View batch stock and expiry",
        "quotations_manage": "Manage quotations",
    },
    "sales": {
        "sales_process": "Process sales",
        "sales_discount": "Apply discounts",
        "sales_price_override": "Override prices",
        "sales_refund": "Refund transactions",
        "sales_cancel": "Cancel transactions",
        "sales_receipt_reprint": "Reprint receipts",
        "sales_history_view": "View sales history",
    },
    "products": {
        "products_add": "Add products",
        "products_edit": "Edit products",
        "products_delete": "Delete products",
        "categories_manage": "Manage categories",
        "variants_manage": "Manage variants",
        "composites_manage": "Manage composite products",
        "product_costs_view": "View product costs",
    },
    "inventory": {
        "inventory_receive": "Receive stock",
        "inventory_adjust": "Adjust stock",
        "inventory_transfer": "Transfer stock",
        "inventory_count": "Perform stock counts",
        "inventory_valuation_view": "View inventory valuation",
    },
    "financial": {
        "tips_collect": "Record customer tips",
        "tips_manage": "Configure tips and reverse tip payments",
        "tips_payout": "Record employee tip payouts",
        "tips_reports_view": "View tip entitlements and reports",
        "revenue_view": "View revenue",
        "profits_view": "View profits",
        "expenses_manage": "Manage expenses",
        "shifts_open": "Open shifts",
        "shifts_close": "Close shifts",
        "z_reports_view": "View Z Reports",
        "cash_movements_manage": "Manage cash movements",
    },
    "management": {
        "employees_manage": "Manage employees",
        "roles_manage": "Manage roles",
        "branches_manage": "Manage branches",
        "devices_manage": "Manage devices",
        "printers_manage": "Manage printers",
        "business_settings_manage": "Change business settings",
        "audit_logs_view": "View activity logs",
        "approve_restricted_actions": "Approve restricted actions",
    },
}

PERMISSION_KEYS = frozenset(
    key for group in PERMISSION_GROUPS.values() for key in group
)

# Existing API checks remain valid while new screens and endpoints use the
# granular names. Both forms are emitted in authorization snapshots.
LEGACY_TO_GRANULAR: dict[str, tuple[str, ...]] = {
    "sales": ("sales_process", "sales_history_view", "sales_receipt_reprint"),
    "discounts": ("sales_discount",),
    "refunds": ("sales_refund",),
    "manage_inventory": (
        "inventory_receive", "inventory_adjust", "inventory_transfer",
        "inventory_count",
    ),
    "inventory_valuation": ("inventory_valuation_view",),
    "manage_products": (
        "products_add", "products_edit", "products_delete",
        "categories_manage", "variants_manage", "composites_manage",
        "product_costs_view",
    ),
    "reports": ("revenue_view", "profits_view", "z_reports_view"),
    "employees": ("employees_manage", "roles_manage", "audit_logs_view"),
    "settings": ("business_settings_manage", "printers_manage"),
    "manage_devices": ("devices_manage",),
}

LEGACY_KEYS = frozenset({
    *LEGACY_TO_GRANULAR,
    "customers_view", "customers_manage", "credit_sales",
    "credit_settlements", "expenses_create", "expense_reports",
    "currencies_manage",
})


def _permissions(*enabled: str) -> dict[str, bool]:
    return {key: key in enabled for key in PERMISSION_KEYS}


ALL = tuple(PERMISSION_KEYS)
ROLE_TEMPLATES: dict[str, dict[str, bool]] = {
    "owner": _permissions(*ALL),
    "administrator": _permissions(*ALL),
    "branch_manager": _permissions(
        *(key for key in ALL if key not in {
            "roles_manage", "devices_manage", "business_settings_manage",
        })
    ),
    "supervisor": _permissions(
        "sales_process", "sales_discount", "sales_price_override",
        "sales_refund", "sales_cancel", "sales_receipt_reprint",
        "sales_history_view", "inventory_receive", "inventory_adjust",
        "inventory_transfer", "inventory_count", "revenue_view",
        "expenses_manage", "shifts_open", "shifts_close", "z_reports_view",
        "cash_movements_manage", "approve_restricted_actions",
    ),
    "cashier": _permissions(
        "tips_collect",
        "sales_process", "sales_receipt_reprint", "sales_history_view",
        "shifts_open", "shifts_close", "cash_movements_manage", "z_reports_view",
        "orders_settle",
    ),
    "inventory_clerk": _permissions(
        "inventory_receive", "inventory_adjust", "inventory_transfer",
        "inventory_count", "inventory_valuation_view", "products_add",
        "products_edit", "categories_manage", "variants_manage",
        "composites_manage",
    ),
    "accountant": _permissions(
        "tips_reports_view",
        "sales_history_view", "revenue_view", "profits_view",
        "expenses_manage", "z_reports_view", "inventory_valuation_view",
        "audit_logs_view",
    ),
    "waiter": _permissions("sales_process", "sales_history_view", "orders_manage", "orders_send", "tips_collect"),
    "kitchen_staff": _permissions("kitchen_view", "kitchen_update"),
    "bartender": _permissions("orders_manage", "orders_send", "bar_view", "bar_update"),
    "restaurant_manager": _permissions("restaurant_manage", "orders_manage", "orders_send", "orders_settle", "kitchen_view", "kitchen_update", "bar_view", "bar_update", "sales_process", "sales_history_view", "sales_receipt_reprint", "sales_discount", "sales_refund", "shifts_open", "shifts_close", "printers_manage", "approve_restricted_actions", "revenue_view"),
    "hotel_staff": _permissions("hospitality_manage", "orders_manage", "orders_send", "customers_view"),
}

# Legacy role names continue to have their previous meaning.
ROLE_ALIASES = {"manager": "branch_manager"}


def role_template(role: str) -> dict[str, bool]:
    return dict(ROLE_TEMPLATES.get(ROLE_ALIASES.get(role, role), _permissions()))


def normalize_permissions(role: str, supplied: Mapping[str, bool] | None) -> dict[str, bool]:
    result = role_template(role)
    supplied = supplied or {}
    for key in PERMISSION_KEYS:
        if key in supplied:
            result[key] = bool(supplied[key])
    for legacy, granular in LEGACY_TO_GRANULAR.items():
        if legacy in supplied:
            for key in granular:
                if key not in supplied:
                    result[key] = bool(supplied[legacy])
    # Emit legacy keys for older POS and Backoffice builds.
    for legacy, granular in LEGACY_TO_GRANULAR.items():
        result[legacy] = (all if legacy == "reports" else any)(result.get(key, False) for key in granular)
    for key in LEGACY_KEYS - LEGACY_TO_GRANULAR.keys():
        if key in supplied:
            result[key] = bool(supplied[key])
    if "expenses_manage" in supplied and "expenses_create" not in supplied:
        result["expenses_create"] = bool(supplied["expenses_manage"])
    # Existing non-Phase-7B domains retain established role defaults.
    elevated = ROLE_ALIASES.get(role, role) in {"owner", "administrator", "branch_manager"}
    result.setdefault("customers_view", role not in {"kitchen_staff", "denied"})
    result.setdefault("customers_manage", elevated)
    result.setdefault("credit_sales", elevated)
    result.setdefault("credit_settlements", elevated)
    result.setdefault("expenses_create", role not in {"kitchen_staff", "denied"})
    result.setdefault("expense_reports", elevated)
    result.setdefault("currencies_manage", elevated)
    return result


def has_permission(permissions: Mapping[str, bool] | None, key: str) -> bool:
    permissions = permissions or {}
    if key in permissions:
        return permissions[key] is True
    granular = LEGACY_TO_GRANULAR.get(key)
    if granular:
        return any(permissions.get(item) is True for item in granular)
    for legacy, mapped in LEGACY_TO_GRANULAR.items():
        if key in mapped and permissions.get(legacy) is True:
            return True
    return False
