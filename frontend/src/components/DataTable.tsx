import { Box, Checkbox, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow } from "@mui/material";
import type { ReactNode } from "react";
import { Empty, Loading } from "./Feedback";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Row = Record<string, any>;

export interface Column<T = Row> {
  key: string;
  label: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  width?: number | string;
  hideOnMobile?: boolean;
}

interface Props<T = Row> {
  columns: Column<T>[];
  rows: T[];
  loading?: boolean;
  onRowClick?: (row: T) => void;
  rowKey?: (row: T) => string | number;
  emptyTitle?: string;
  emptyHint?: string;
  count?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  selectable?: boolean;
  selected?: (string | number)[];
  onSelect?: (ids: (string | number)[]) => void;
  dense?: boolean;
  footer?: ReactNode;
}

export function DataTable({ columns, rows, loading, onRowClick, rowKey,
  emptyTitle, emptyHint, count, page, pageSize = 25, onPageChange, onPageSizeChange, selectable, selected = [],
  onSelect, dense, footer }: Props<Row>) {
  const keyOf = rowKey || ((r: Row) => (r.id as string | number));
  const allIds = rows.map(keyOf);
  const allSelected = selectable && rows.length > 0 && allIds.every((id) => selected.includes(id));
  return (
    <Box>
      <TableContainer sx={{ overflowX: "auto" }}>
        <Table size={dense ? "small" : "medium"} stickyHeader>
          <TableHead>
            <TableRow>
              {selectable && (
                <TableCell padding="checkbox">
                  <Checkbox checked={!!allSelected} indeterminate={!allSelected && selected.length > 0}
                    onChange={() => onSelect?.(allSelected ? [] : allIds)} />
                </TableCell>
              )}
              {columns.map((c) => (
                <TableCell key={c.key} align={c.align} sx={{ width: c.width, display: c.hideOnMobile ? { xs: "none", md: "table-cell" } : undefined }}>
                  {c.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {!loading && rows.map((row) => {
              const id = keyOf(row);
              return (
                <TableRow key={id} hover onClick={onRowClick ? () => onRowClick(row) : undefined}
                  sx={{ cursor: onRowClick ? "pointer" : undefined }}>
                  {selectable && (
                    <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                      <Checkbox checked={selected.includes(id)}
                        onChange={() => onSelect?.(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id])} />
                    </TableCell>
                  )}
                  {columns.map((c) => (
                    <TableCell key={c.key} align={c.align} sx={{ display: c.hideOnMobile ? { xs: "none", md: "table-cell" } : undefined }}>
                      {c.render ? c.render(row) : (row[c.key] as ReactNode) ?? "—"}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}
            {footer}
          </TableBody>
        </Table>
      </TableContainer>
      {loading && <Loading />}
      {!loading && rows.length === 0 && <Empty title={emptyTitle || "No records found"} hint={emptyHint} />}
      {onPageChange && count !== undefined && (
        <TablePagination component="div" count={count} page={(page || 1) - 1} rowsPerPage={pageSize}
          rowsPerPageOptions={[25, 50, 100]} onPageChange={(_, p) => onPageChange(p + 1)}
          onRowsPerPageChange={(e) => onPageSizeChange?.(Number(e.target.value))} />
      )}
    </Box>
  );
}
