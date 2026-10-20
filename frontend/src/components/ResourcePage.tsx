import Add from "@mui/icons-material/Add";
import DeleteOutline from "@mui/icons-material/DeleteOutline";
import EditOutlined from "@mui/icons-material/EditOutlined";
import Search from "@mui/icons-material/Search";
import { Box, Button, Card, IconButton, InputAdornment, Stack, TextField, Tooltip } from "@mui/material";
import { useState, type ReactNode } from "react";
import { api } from "../api/client";
import { useApi, useInvalidate, type Params } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { DataTable, type Column } from "./DataTable";
import { ConfirmDialog, ErrorAlert, useToast } from "./Feedback";
import { FormDialog, type FieldDef } from "./FormDialog";
import { PageHeader } from "./PageHeader";

type Row = Record<string, unknown>;

export interface ResourceProps {
  title: string;
  subtitle?: ReactNode;
  url: string; // e.g. "/org/departments/"
  columns: Column<Row>[];
  fields?: FieldDef[];
  writePerm?: string | string[];
  params?: Params;
  searchable?: boolean;
  canDelete?: boolean;
  canEdit?: boolean;
  canCreate?: boolean;
  createLabel?: string;
  toInitial?: (row: Row) => Row;
  rowActions?: (row: Row) => ReactNode;
  headerActions?: ReactNode;
  onRowClick?: (row: Row) => void;
  embedded?: boolean;
  defaults?: Row;
  intro?: ReactNode;
  filters?: ReactNode;
}

export function ResourcePage(p: ResourceProps) {
  const { can } = useAuth();
  const toast = useToast();
  const invalidate = useInvalidate();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [editing, setEditing] = useState<Row | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Row | null>(null);
  const q = useApi<{ count: number; results: Row[] } | Row[]>(p.url, { ...p.params, search, page, page_size: pageSize });
  const rows = Array.isArray(q.data) ? q.data : q.data?.results || [];
  const count = Array.isArray(q.data) ? undefined : q.data?.count;
  const writable = !p.writePerm || can(p.writePerm);
  const fields = p.fields || [];

  const actions: Column<Row>[] = writable && (p.canEdit !== false || p.canDelete || p.rowActions) && fields.length ? [{
    key: "_actions", label: "", align: "right", render: (row) => (
      <Stack direction="row" spacing={0.5} justifyContent="flex-end" onClick={(e) => e.stopPropagation()}>
        {p.rowActions?.(row)}
        {p.canEdit !== false && (
          <Tooltip title="Edit"><IconButton size="small" onClick={() => setEditing(row)}><EditOutlined fontSize="small" /></IconButton></Tooltip>
        )}
        {p.canDelete && (
          <Tooltip title="Delete"><IconButton size="small" onClick={() => setDeleting(row)}><DeleteOutline fontSize="small" /></IconButton></Tooltip>
        )}
      </Stack>
    ),
  }] : p.rowActions ? [{ key: "_actions", label: "", align: "right", render: (row) => (
    <Stack direction="row" spacing={0.5} justifyContent="flex-end" onClick={(e) => e.stopPropagation()}>{p.rowActions?.(row)}</Stack>) }] : [];

  const refresh = () => invalidate(p.url);
  const createBtn = writable && p.canCreate !== false && fields.length ? (
    <Button variant="contained" startIcon={<Add />} onClick={() => setCreating(true)}>{p.createLabel || "Add"}</Button>
  ) : null;

  const body = (
    <>
      {(p.searchable !== false || p.filters) && (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ p: 1.5 }}>
          {p.searchable !== false && (
            <TextField placeholder="Search…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
              sx={{ minWidth: 260 }} />
          )}
          {p.filters}
          <Box flex={1} />
          {p.embedded && p.headerActions}
          {p.embedded && createBtn}
        </Stack>
      )}
      <ErrorAlert error={q.error} />
      <DataTable columns={[...p.columns, ...actions]} rows={rows} loading={q.isLoading} onRowClick={p.onRowClick}
        count={count} page={page} pageSize={pageSize} onPageChange={count !== undefined ? setPage : undefined}
        onPageSizeChange={(s) => { setPageSize(s); setPage(1); }} dense />
    </>
  );

  return (
    <Box>
      {!p.embedded && (
        <PageHeader title={p.title} subtitle={p.subtitle} actions={<>{p.headerActions}{createBtn}</>} />
      )}
      {p.embedded ? body : <Card>{body}</Card>}
      {fields.length > 0 && (
        <>
          <FormDialog open={creating} title={`${p.createLabel || "Add"} — ${p.title}`} fields={fields} intro={p.intro}
            initial={p.defaults} onClose={() => setCreating(false)}
            onSubmit={async (data) => { await api.post(p.url, data); toast.ok("Saved."); refresh(); }} />
          <FormDialog open={!!editing} title={`Edit — ${p.title}`} fields={fields} intro={p.intro}
            initial={editing ? (p.toInitial ? p.toInitial(editing) : editing) : undefined} onClose={() => setEditing(null)}
            onSubmit={async (data) => { await api.patch(`${p.url}${editing?.id}/`, data); toast.ok("Updated."); refresh(); }} />
        </>
      )}
      <ConfirmDialog open={!!deleting} title="Delete record?" color="error" confirmLabel="Delete"
        message="This cannot be undone." onClose={() => setDeleting(null)}
        onConfirm={async () => { await api.delete(`${p.url}${deleting?.id}/`); toast.ok("Deleted."); refresh(); }} />
    </Box>
  );
}
