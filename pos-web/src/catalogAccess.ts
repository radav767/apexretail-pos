import { isPrivilegedSalesActor, type SalesHistoryActor } from "./salesHistory";

// Explicit granular denials take precedence over backwards-compatible aliases.
export function catalogPermission(actor: SalesHistoryActor | null, permission: string): boolean {
  return isPrivilegedSalesActor(actor) ||
    (actor?.permissions?.[permission] ?? actor?.permissions?.manage_products) === true;
}

export function canManageProductTool(actor: SalesHistoryActor | null, feature: string): boolean {
  const permission = feature === "categories" ? "categories_manage"
    : feature === "composite-products" ? "composites_manage"
      : feature === "product-variants" ? "variants_manage"
        : feature === "import-export" ? "products_add" : "products_edit";
  return catalogPermission(actor, permission);
}
