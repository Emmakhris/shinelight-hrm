import { Button, Card, CardContent, Grid2 as Grid, LinearProgress, MenuItem, Stack, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { BarList, ChartTitle } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";
import { EXIT_TYPES, REASONS } from "./ExitForms";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function Analytics() {
  const q = useApi<R>("/offboarding/analytics/");
  const d = q.data;
  if (!d) return null;
  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Exits (12 months)", d.exits], ["Turnover", `${d.turnover_percent}%`], ["Voluntary", d.voluntary], ["Involuntary", d.involuntary],
          ["Regretted resignations", d.regretted_resignations], ["Left within a year", d.early_attrition], ["Would recommend us", d.would_recommend_percent == null ? "—" : `${d.would_recommend_percent}%`],
          ["Avg clearance (days)", d.avg_clearance_days ?? "—"]].map(([l, v]) => <Grid key={l} size={{ xs: 6, md: 3 }}><Kpi label={l} value={v} /></Grid>)}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Reasons for leaving</ChartTitle><BarList data={d.by_reason} valueLabel="Exits" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Exit type</ChartTitle><BarList data={d.by_type} valueLabel="Exits" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Length of service at exit</ChartTitle><BarList data={d.by_tenure} valueLabel="Exits" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Exit interview ratings (out of 5)</ChartTitle><BarList data={d.exit_ratings} valueLabel="Average" /></CardContent></Card></Grid>
        <Grid size={12}><Card><CardContent><ChartTitle>Coming up: retirements and contract ends (90 days)</ChartTitle>
          <DataTable dense rows={d.upcoming} rowKey={(r) => r.employee} emptyTitle="None in the next 90 days" columns={[{ key: "name", label: "Employee" }, { key: "department", label: "Department" },
            { key: "kind", label: "Event", render: (r) => (r.kind === "retirement" ? "Compulsory retirement" : "Contract ends") }, { key: "date", label: "Date", render: (r) => fmtDate(r.date) }]} />
        </CardContent></Card></Grid>
      </Grid>
    </>
  );
}

export default function Exits() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [tab, setTab] = useState(0);
  const [status, setStatus] = useState("");
  const [recording, setRecording] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  const manage = can("offboarding.manage");
  return (
    <>
      <PageHeader title="Exits & offboarding" subtitle="Resignations, retirements and terminations, clearance across departments, and turnover analytics."
        actions={manage && <Button variant="contained" onClick={() => setRecording(true)}>Record exit</Button>} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Exits" /><Tab label="Clearance for me" />{manage && <Tab label="Turnover analytics" />}</Tabs>
      {tab < 2 && <Card><ResourcePage embedded title="Exit" url="/offboarding/separations/" params={tab === 1 ? { clearance_for_me: 1 } : { status }} canCreate={false} canEdit={false}
        onRowClick={(r) => nav(`/offboarding/${r.id}`)}
        filters={tab === 0 ? <TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 170 }}>
          <MenuItem value="">All</MenuItem>{[["pending", "Pending approval"], ["clearance", "Clearance"], ["completed", "Completed"], ["withdrawn", "Withdrawn"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
        </TextField> : undefined}
        columns={[{ key: "employee_name", label: "Employee", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.job_title} · {r.department_name}</small></> },
          { key: "exit_type_label", label: "Type", render: (r) => <>{r.exit_type_label}<br /><small>{r.reason_label}</small></> },
          { key: "last_working_day", label: "Last day", render: (r) => fmtDate(r.last_working_day) },
          { key: "progress", label: "Clearance", render: (r) => (r.progress.total ? <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 120 }}>
            <LinearProgress variant="determinate" value={(100 * r.progress.done) / r.progress.total} sx={{ flex: 1, height: 8, borderRadius: 4 }} /><small>{r.progress.done}/{r.progress.total}</small></Stack> : "—") },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "clearance" ? "in_progress" : r.status} label={r.status_label} /> }]} /></Card>}
      {tab === 2 && <Analytics />}
      <FormDialog open={recording} title="Record an exit" onClose={() => setRecording(false)} initial={{ exit_type: "resignation", rehire_eligible: true, notice_date: new Date().toISOString().slice(0, 10) }}
        fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", required: true },
          { name: "exit_type", label: "Type of exit", type: "select", required: true, options: EXIT_TYPES, width: 6 },
          { name: "reason", label: "Reason", type: "select", options: REASONS, width: 6 },
          { name: "notice_date", label: "Notice given on", type: "date", width: 6 }, { name: "last_working_day", label: "Last working day", type: "date", required: true, width: 6 },
          { name: "details", label: "Details / grounds (required for involuntary exits)", type: "textarea" },
          { name: "handover_to", label: "Hand over to", type: "ref", ref: "/directory/", width: 6 },
          { name: "rehire_eligible", label: "Eligible for rehire", type: "checkbox", width: 6 }]}
        onSubmit={async (v) => { const r = await api.post<R>("/offboarding/separations/", v); toast.ok(`Exit ${r.data.reference} sent for approval.`); inv("/offboarding/"); }} />
    </>
  );
}
