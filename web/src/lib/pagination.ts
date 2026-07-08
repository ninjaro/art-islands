export interface PageResult<T> {
  pageItems: T[];
  page: number;
  pageCount: number;
  totalItems: number;
}

export function clampPage(page: number, totalItems: number, pageSize: number): number {
  const size = Math.max(1, Math.floor(pageSize) || 1);
  const pageCount = Math.max(1, Math.ceil(totalItems / size));
  const wanted = Math.floor(page) || 1;
  return Math.min(Math.max(1, wanted), pageCount);
}

export function paginate<T>(items: T[], page: number, pageSize: number): PageResult<T> {
  const size = Math.max(1, Math.floor(pageSize) || 1);
  const totalItems = items.length;
  const pageCount = Math.max(1, Math.ceil(totalItems / size));
  const current = clampPage(page, totalItems, size);
  return {
    pageItems: items.slice((current - 1) * size, current * size),
    page: current,
    pageCount,
    totalItems,
  };
}
