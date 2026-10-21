import { Button, Card, CardContent, Grid2 as Grid, MenuItem, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { BarList, ChartTitle, Columns } from "../../components/Charts";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
export const CASE_TYPES = [["grievance", "Grievance"], ["harassment", "Harassment / bullying"], ["misconduct", "Misconduct"], ["disciplinary", "Disciplinary"],
  ["conflict", "Workplace conflict"], ["policy_violation", "Policy violation"], ["whistleblowing", "Whistleblowing"]].map(([value, label]) => ({ value, label }));
const SEV_COLOR: Record<string, string> = { critical: "#b91c1c", high: "#b45309", medium: "#2a78d6", low: "#52514e" };

function Report() {
  const q = useApi<R>("/relations/report/");
  const d = q.data;
  if (!d) return null;
  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Cases this year", d.cases], ["Open", d.open], ["Overdue", d.overdue], ["Avg days to close", d.avg_days_to_close ?? "—"], ["Appeals", d.appeals]].map(([l, v]) => (
          <Grid key={l} size={{ xs: 6, md: 2.4 }}><Kpi label={l} value={v} color={l === "Overdue" && v ? "#b45309" : undefined} /></Grid>))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Cases by month</ChartTitle><Columns data={d.by_month} valueLabel="Cases" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>By type</ChartTitle><BarList data={d.by_type} valueLabel="Cases" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Outcomes</ChartTitle><BarList data={d.by_outcome} valueLabel="Cases" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Departments of respondents</ChartTitle><BarList data={d.by_department} valueLabel="Cases" /></CardContent></Card></Grid>
      </Grid>
    </>
  );
}

export default function Cases() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [tab, setTab] = useState(0);
  const [status, setStatus] = useState("");
  const [registering, setRegistering] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Employee relations" subtitle="Confidential cases assigned to you. Access is by assignment only and every view is audited."
        actions={<Button variant="contained" onClick={() => setRegistering(true)}>Register case</Button>} />
      {can("relations.view_all") && <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Cases" /><Tab label="Trends" /></Tabs>}
      {tab === 0 && <Card><ResourcePage embedded title="Case" url="/relations/cases/" params={{ status }} canCreate={false} canEdit={false}
        onRowClick={(r) => nav(`/relations/cases/${r.id}`)}
        filters={<TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 190 }}>
          <MenuItem value="">All</MenuItem>{[["reported", "Reported"], ["investigating", "Investigating"], ["hearing", "Hearing / mediation"], ["pending_decision", "Awaiting approval"], ["decided", "Decided"], ["appeal", "Appeal"], ["closed", "Closed"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
        </TextField>}
        columns={[{ key: "reference", label: "Ref", render: (r) => <b>{r.reference}</b> },
          { key: "case_type_label", label: "Type", render: (r) => <>{r.case_type_label}<br /><small style={{ color: SEV_COLOR[r.severity] }}>{r.severity}</small></> },
          { key: "title", label: "Subject" },
          { key: "respondent_names", label: "Respondent(s)", hideOnMobile: true, render: (r) => r.respondent_names.join(", ") || "—" },
          { key: "case_officer_name", label: "Officer", hideOnMobile: true },
          { key: "due_date", label: "Due", render: (r) => <span style={{ color: r.overdue ? "#b91c1c" : undefined }}>{fmtDate(r.due_date)}</span> },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "closed" ? "completed" : "in_progress"} label={r.status_label} /> }]} /></Card>}
      {tab === 1 && <Report />}
      <FormDialog open={registering} title="Register a case" onClose={() => setRegistering(false)} initial={{ case_type: "misconduct", severity: "medium", respondents: [] }}
        fields={[{ name: "case_type", label: "Type", type: "select", required: true, options: CASE_TYPES, width: 6 },
          { name: "severity", label: "Severity", type: "select", width: 6, options: [["low", "Low"], ["medium", "Medium"], ["high", "High"], ["critical", "Critical"]].map(([value, label]) => ({ value, label })) },
          { name: "title", label: "Subject", required: true }, { name: "description", label: "Allegation / details", type: "textarea", required: true },
          { name: "respondents", label: "Respondent(s)", type: "multiref", ref: "/employees/", refLabel: (e) => String(e.full_name) },
          { name: "complainant", label: "Complainant (if any)", type: "ref", ref: "/employees/", width: 6 },
          { name: "incident_date", label: "Incident date", type: "date", width: 6 }, { name: "policy_reference", label: "Policy / code clause" }]}
        onSubmit={async (v) => { const r = await api.post<R>("/relations/cases/", v); toast.ok(`Case ${r.data.reference} registered.`); inv("/relations/"); nav(`/relations/cases/${r.data.id}`); }} />
    </>
  );
}
