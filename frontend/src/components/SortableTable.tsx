import { useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  initialSort?: { key: string; dir: "asc" | "desc" };
  rowAction?: (row: T) => ReactNode;
  empty?: string;
}

export function SortableTable<T,>({
  rows,
  columns,
  rowKey,
  initialSort,
  rowAction,
  empty = "No rows.",
}: Props<T>) {
  const [sort, setSort] = useState(
    initialSort ?? { key: columns[0]?.key ?? "", dir: "desc" as const },
  );

  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;
    const factor = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = column.sortValue!(a);
      const bv = column.sortValue!(b);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
      return String(av).localeCompare(String(bv)) * factor;
    });
  }, [rows, columns, sort]);

  const clickHeader = (key: string) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" },
    );
  };

  if (!rows.length) {
    return <div className="empty-state">{empty}</div>;
  }

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.align === "right" ? "num" : undefined}
                onClick={() => clickHeader(column.key)}
              >
                {column.header}
                {sort.key === column.key && (
                  <span className="sort-ind">{sort.dir === "asc" ? "▲" : "▼"}</span>
                )}
              </th>
            ))}
            {rowAction && <th className="num">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={column.align === "right" ? "num" : undefined}
                >
                  {column.render(row)}
                </td>
              ))}
              {rowAction && <td className="num">{rowAction(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
