export type PageMeta = { page: number; page_size: number; total: number; total_pages: number };

export const emptyPage = (pageSize = 25): PageMeta => ({ page: 1, page_size: pageSize, total: 0, total_pages: 0 });

export function unpackPage<T>(data: T[] | ({ items: T[] } & PageMeta)): { items: T[]; meta: PageMeta } {
  if (Array.isArray(data)) return { items: data, meta: { page: 1, page_size: data.length || 25, total: data.length, total_pages: data.length ? 1 : 0 } };
  return { items: data.items, meta: data };
}
