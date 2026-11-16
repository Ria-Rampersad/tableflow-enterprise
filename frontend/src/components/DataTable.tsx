import { useMemo, useState, type ReactNode } from 'react';
import { Empty } from './ui';

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  align?: 'left' | 'right' | 'center';
  width?: string;
}

/**
 * Generic table with client-side sorting, row click (drill-down) and optional server pagination.
 * Kept dependency-free on purpose - every list screen in TableFlow uses it.
 */
export function DataTable<T>({ rows, columns, onRowClick, rowKey, empty, total, page, pageSize, onPage, dense }: {
  rows: T[]; columns: Column<T>[]; onRowClick?: (row: T) => void; rowKey: (row: T) => string | number;
  empty?: ReactNode; total?: number; page?: number; pageSize?: number; onPage?: (page: number) => void; dense?: boolean;
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const val = col.sortValue ?? ((r: T) => (r as any)[col.key]);
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b);
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }, [rows, columns, sort]);

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? (s.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 }));

  if (!rows.length) return <Empty>{empty}</Empty>;
  const pages = total && pageSize ? Math.ceil(total / pageSize) : 0;
  return (
    <div className="table-wrap">
      <table className={`table ${dense ? 'dense' : ''}`}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: c.align ?? 'left', width: c.width }}>
                <button type="button" className="th-btn" onClick={() => toggle(c.key)}>
                  {c.header}{sort?.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)} onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? 'clickable' : ''}>
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align ?? 'left' }}>
                  {c.render ? c.render(row) : String((row as any)[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pages > 1 && onPage && page !== undefined && (
        <div className="pager">
          <span className="muted small">{total?.toLocaleString('en-ZA')} records · page {page + 1} of {pages}</span>
          <div className="row gap-sm">
            <button className="btn btn-secondary" disabled={page === 0} onClick={() => onPage(page - 1)}>Previous</button>
            <button className="btn btn-secondary" disabled={page + 1 >= pages} onClick={() => onPage(page + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  );
}
