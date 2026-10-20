import Add from "@mui/icons-material/Add";
import { Button, Card, Chip, MenuItem, Stack, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi, useList } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { fmtDateTime, titleCase } from "../../utils";
import { NewRequestDialog } from "./HelpDesk";

const PRIORITY_COLORS: Record<string, "default" | "warning" | "error" | "info"> = { low: "default", normal: "info", high: "warning", urgent: "error" };

export default function Queue() {
  const [view, setView] = useState("assigned");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [logging, setLogging] = useState(false);
  const cats = useList<{ id: number; name: string }>("/helpdesk/categories/");
  const q = useApi<{ count: number; results: Record<string, unknown>[] }>("/helpdesk/tickets/",
    { view: view === "all" ? undefined : view, search, service_type__category: category, page, ordering: "resolution_due" });
  const nav = useNavigate();
  return (
    <>
      <PageHeader title="Service desk queue" subtitle="Work tickets by SLA. Internal notes are never shown to employees."
        actions={<Button variant="contained" startIcon={<Add />} onClick={() => setLogging(true)}>Log request (phone / walk-in)</Button>} />
      <Tabs value={view} onChange={(_, v) => { setView(v); setPage(1); }} sx={{ mb: 1 }} variant="scrollable">
        {[["assigned", "Assigned to me"], ["unassigned", "Unassigned"], ["overdue", "Overdue"], ["open", "All open"], ["all", "All tickets"]]
          .map(([v, l]) => <Tab key={v} value={v} label={l} />)}
      </Tabs>
      <Card>
        <Stack direction="row" spacing={1} sx={{ p: 1.5 }}>
          <TextField placeholder="Reference, subject, employee…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} sx={{ minWidth: 260 }} />
          <TextField select label="Category" value={category} onChange={(e) => setCategory(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">All</MenuItem>{cats.items.map((c) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}
          </TextField>
        </Stack>
        <DataTable dense loading={q.isLoading} rows={q.data?.results || []} count={q.data?.count} page={page} onPageChange={setPage}
          onRowClick={(r) => nav(`/helpdesk/tickets/${r.id}`)} emptyTitle="Queue is clear"
          columns={[{ key: "reference", label: "Ref" }, { key: "subject", label: "Subject" }, { key: "requester_name", label: "Requester" },
            { key: "service_name", label: "Service", hideOnMobile: true },
            { key: "priority", label: "Priority", render: (r) => <Chip variant="outlined" color={PRIORITY_COLORS[r.priority]} label={titleCase(r.priority)} /> },
            { key: "assignee_name", label: "Agent", hideOnMobile: true },
            { key: "resolution_due", label: "Due", render: (r) => r.is_overdue ? <Chip color="error" label={fmtDateTime(r.resolution_due)} /> : fmtDateTime(r.resolution_due) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]} />
      </Card>
      <NewRequestDialog open={logging} onClose={() => setLogging(false)} />
    </>
  );
}
