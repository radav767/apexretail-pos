import "./pagination.css";
import type { PageMeta } from "./pagination";

export default function Pagination({ meta, onPage }: { meta: PageMeta; onPage: (page: number) => void }) {
  return <nav className="report-pagination" aria-label="Report pagination">
    <span>{meta.total} record{meta.total === 1 ? "" : "s"}</span>
    <div>
      <button type="button" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>Previous</button>
      <span>Page {meta.page} of {Math.max(meta.total_pages, 1)}</span>
      <button type="button" disabled={meta.page >= meta.total_pages} onClick={() => onPage(meta.page + 1)}>Next</button>
    </div>
  </nav>;
}
