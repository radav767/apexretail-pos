import { api } from "./api/client";
import type { CreditCustomer } from "./creditSale";

export async function searchCustomers(
  companyId: string,
  search = "",
  options: { activeOnly?: boolean; limit?: number } = {},
): Promise<CreditCustomer[]> {
  const activeOnly = options.activeOnly ?? false;
  const response = await api.get(`/customers/${companyId}`, {
    params: {
      search: search.trim() || undefined,
      active: activeOnly ? true : undefined,
      limit: options.limit ?? 500,
    },
  });
  const rows = Array.isArray(response.data) ? response.data : [];
  return activeOnly ? rows.filter((customer: CreditCustomer) => customer.active) : rows;
}
