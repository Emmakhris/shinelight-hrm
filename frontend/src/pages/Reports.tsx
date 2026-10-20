import Download from "@mui/icons-material/Download";
import PlayArrow from "@mui/icons-material/PlayArrow";
import { Alert, Button, Card, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";
import { api, download } from "../api/client";
import { useApi } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/DataTable";
import { ErrorAlert, useToast } from "../components/Feedback";
import { PageHeader, Section } from "../components/PageHeader";
import { ResourcePage } from "../components/ResourcePage";
import { fmtDateTime } from "../utils";

export default function Reports() {
  const { can } = useAuth();
  const toast = useToast();
  const catalog = useApi<{ code: string; name: string }[]>("/reports/catalog/");
  const [code, setCode] = useState("headcount");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [result, setResult] = useState<{ headers: string[]; rows: unknown[][] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const params = { start: start || undefined, end: end || undefined };

  const run = async () => {
    setError(null);
    try {
      setResult((await api.get(`/reports/run/${code}/`, { params })).data);
    } catch (e) { setError(e); }
  };
  const exportIt = async () => {
    try {
      await download(`/reports/run/${code}/`, { ...params, format: "xlsx" }, `${code}.xlsx`);
    } catch (e) {
      if (!can("reports.export")) {
        const reason = window.prompt("Exports need approval. Reason for this export:");
        if (reason) {
          await api.post("/reports/export-requests/", { report_code: code, params, reason });
          toast.ok("Export request submitted for approval.");
        }
      } else toast.error(e);
    }
  };
  const rows = (result?.rows || []).map((r, i) => Object.fromEntries([["id", i], ...r.map((v, j) => [`c${j}`, v])]));
  return (
    <>
      <PageHeader title="Reports" subtitle="Standard HR reports within your data scope. Exports are logged." />
      <Section>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <TextField select label="Report" value={code} onChange={(e) => { setCode(e.target.value); setResult(null); }} sx={{ minWidth: 320 }}>
            {(catalog.data || []).map((r) => <MenuItem key={r.code} value={r.code}>{r.name}</MenuItem>)}
          </TextField>
          <TextField type="date" label="From" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
          <TextField type="date" label="To" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
          <Button variant="contained" startIcon={<PlayArrow />} onClick={run}>Run</Button>
          <Button variant="outlined" startIcon={<Download />} onClick={exportIt}>Export to Excel</Button>
        </Stack>
      </Section>
      <ErrorAlert error={error} />
      {result && (
        <Card>
          <DataTable dense rows={rows} columns={result.headers.map((h, j) => ({ key: `c${j}`, label: h }))} />
        </Card>
      )}
      {!can("reports.export") && <Alert severity="info" sx={{ mt: 2 }}>Bulk exports require approval by an authorised officer.</Alert>}
      <Section title="Export requests">
        <ResourcePage embedded title="Export requests" url="/reports/export-requests/" searchable={false}
          columns={[{ key: "report_code", label: "Report" }, { key: "requested_by", label: "Requested by" },
            { key: "reason", label: "Reason" }, { key: "status", label: "Status" },
            { key: "created_at", label: "When", render: (r) => fmtDateTime(r.created_at as string) }]}
          rowActions={(r) => r.status === "pending" && can("reports.export") ? (
            <>
              <Button size="small" onClick={async () => { await api.post(`/reports/export-requests/${r.id}/decide/`, { approve: true }); toast.ok("Approved"); }}>Approve</Button>
              <Button size="small" color="error" onClick={async () => { await api.post(`/reports/export-requests/${r.id}/decide/`, { approve: false }); toast.ok("Rejected"); }}>Reject</Button>
            </>
          ) : r.status === "approved" ? (
            <Button size="small" onClick={() => download(`/reports/run/${r.report_code}/`, { format: "xlsx", export_request: r.id as number })}>Download</Button>
          ) : null} />
      </Section>
    </>
  );
}
