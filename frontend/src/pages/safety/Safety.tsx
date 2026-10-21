import { Alert, Button, Card, CardContent, Grid2 as Grid, MenuItem, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { BarList, ChartTitle, Columns } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const opts = (p: string[][]) => p.map(([value, label]) => ({ value, label }));
export const KINDS = opts([["near_miss", "Near miss"], ["injury", "Injury / accident"], ["exposure", "Occupational exposure (needlestick, splash)"], ["ill_health", "Work-related ill health"],
  ["violence", "Violence / aggression"], ["property", "Property / equipment damage"], ["fire", "Fire"], ["dangerous", "Dangerous occurrence"]]);
export const SEVERITY = opts([["none", "No harm"], ["minor", "Minor (first aid)"], ["moderate", "Moderate (medical treatment)"], ["serious", "Serious (hospital / lost time)"], ["fatal", "Fatal"]]);
const SCALE = [1, 2, 3, 4, 5].map((v) => ({ value: v, label: String(v) }));

export function ReportIncidentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <FormDialog open={open} title="Report an incident or near miss" onClose={onClose} initial={{ kind: "near_miss", severity: "none", persons: [] }}
      intro={<Alert severity="info">Report every incident and near miss — it helps prevent harm. Do not include medical details; occupational health follows up confidentially. For a needlestick or splash, report immediately: post-exposure treatment is time-critical.</Alert>}
      fields={[{ name: "kind", label: "What happened?", type: "select", required: true, options: KINDS, width: 6 },
        { name: "severity", label: "Harm", type: "select", options: SEVERITY, width: 6 },
        { name: "occurred_at", label: "When", type: "datetime", required: true, width: 6 }, { name: "location", label: "Where (ward, room, site)", required: true, width: 6 },
        { name: "department", label: "Department", type: "ref", ref: "/org/departments/", width: 6 },
        { name: "persons", label: "Staff involved", type: "multiref", ref: "/directory/", width: 6 },
        { name: "others_involved", label: "Others involved (patients, visitors, contractors)" },
        { name: "description", label: "Describe what happened", type: "textarea", required: true },
        { name: "immediate_action", label: "Immediate action taken", type: "textarea" }]}
      onSubmit={async (v) => { const r = await api.post<R>("/safety/incidents/", { ...(v as R), occurred_at: new Date((v as R).occurred_at).toISOString() }); toast.ok(`${r.data.detail} Reference ${r.data.reference}.`); inv("/safety/"); }} />
  );
}

function Stats() {
  const q = useApi<R>("/safety/stats/");
  const d = q.data;
  if (!d) return null;
  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Incidents", d.incidents], ["Near misses", d.near_misses], ["Lost-time injuries", d.lost_time_injuries], ["LTIFR (per 1M hours)", d.ltifr ?? "—"],
          ["Days since last LTI", d.days_since_lti ?? "—"], ["Exposures", d.exposures], ["Overdue actions", d.overdue_actions, "#b45309"], ["High residual risks", d.risks_high, "#b91c1c"]].map(([l, v, c]) => (
          <Grid key={l} size={{ xs: 6, md: 3 }}><Kpi label={l} value={v} color={v ? c : undefined} /></Grid>))}
      </Grid>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Reports by month</ChartTitle><Columns data={d.by_month} valueLabel="Reports" /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>By type</ChartTitle><BarList data={d.by_kind} valueLabel="Reports" /></CardContent></Card></Grid>
      </Grid>
    </>
  );
}

export default function Safety() {
  const nav = useNavigate();
  const { can } = useAuth();
  const manage = can("ohs.manage");
  const [tab, setTab] = useState(0);
  const [reporting, setReporting] = useState(false);
  const [status, setStatus] = useState("");
  const [inspecting, setInspecting] = useState<R | null>(null);
  const fitness = useApi<R[]>(tab === 4 ? "/safety/fitness/" : null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Health & safety" subtitle="Incident register, corrective actions, risk assessments, inspections and fitness for duty."
        actions={<Button variant="contained" color="error" onClick={() => setReporting(true)}>Report incident</Button>} />
      <Stats />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable"><Tab label="Incidents" /><Tab label="Corrective actions" /><Tab label="Risk assessments" /><Tab label="Inspections" /><Tab label="Fitness for duty" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Incident" url="/safety/incidents/" params={{ status }} canCreate={false} canEdit={false} onRowClick={(r) => nav(`/safety/incidents/${r.id}`)}
          filters={<TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 170 }}>
            <MenuItem value="">All</MenuItem>{[["reported", "Reported"], ["investigating", "Investigating"], ["actions", "Actions"], ["closed", "Closed"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField>}
          columns={[{ key: "reference", label: "Ref", render: (r) => <b>{r.reference}</b> }, { key: "occurred_at", label: "When", render: (r) => fmtDateTime(r.occurred_at) },
            { key: "kind_label", label: "Type", render: (r) => <>{r.kind_label}<br /><small>{r.severity_label}</small></> },
            { key: "location", label: "Where", hideOnMobile: true, render: (r) => <>{r.location}<br /><small>{r.department_name}</small></> },
            { key: "lost_time_days", label: "Lost days", align: "right", hideOnMobile: true },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "closed" ? "completed" : "in_progress"} label={r.status_label} /> }]} />}
        {tab === 1 && <ResourcePage embedded title="Action" url="/safety/actions/" params={{ status: "open" }} canCreate={false} canEdit={false} searchable={false}
          columns={[{ key: "description", label: "Action", render: (r) => <>{r.description}<br /><small>{r.source}</small></> }, { key: "owner_name", label: "Owner" },
            { key: "due_date", label: "Due", render: (r) => <span style={{ color: new Date(r.due_date) < new Date() ? "#b91c1c" : undefined }}>{fmtDate(r.due_date)}</span> }]}
          rowActions={(r) => <Button size="small" onClick={async () => { await post(`/safety/actions/${r.id}/complete/`, {}); toast.ok("Done."); inv("/safety/"); }}>Mark done</Button>} />}
        {tab === 2 && <ResourcePage embedded title="Risk assessment" url="/safety/risks/" writePerm="ohs.manage" createLabel="Add risk assessment"
          defaults={{ likelihood: 3, severity: 3, residual_likelihood: 2, residual_severity: 2, status: "active" }}
          columns={[{ key: "title", label: "Hazard", render: (r) => <><b>{r.title}</b><br /><small>{r.department_name} · {r.activity}</small></> },
            { key: "risk_score", label: "Risk", align: "right", render: (r) => <span style={{ color: r.risk_score >= 15 ? "#b91c1c" : r.risk_score >= 8 ? "#b45309" : undefined }}>{r.risk_score}</span> },
            { key: "residual_score", label: "Residual", align: "right", render: (r) => <b style={{ color: r.residual_score >= 12 ? "#b91c1c" : undefined }}>{r.residual_score}</b> },
            { key: "review_date", label: "Review", render: (r) => fmtDate(r.review_date) }, { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "review_due" ? "warning" : r.status} label={r.status} /> }]}
          fields={[{ name: "title", label: "Title", required: true, width: 8 }, { name: "department", label: "Department", type: "ref", ref: "/org/departments/", width: 4 },
            { name: "activity", label: "Activity / task", width: 6 }, { name: "who_at_risk", label: "Who is at risk", width: 6 },
            { name: "hazard", label: "Hazard", type: "textarea", required: true },
            { name: "likelihood", label: "Likelihood (1-5)", type: "select", options: SCALE, width: 3 }, { name: "severity", label: "Severity (1-5)", type: "select", options: SCALE, width: 3 },
            { name: "residual_likelihood", label: "Residual likelihood", type: "select", options: SCALE, width: 3 }, { name: "residual_severity", label: "Residual severity", type: "select", options: SCALE, width: 3 },
            { name: "controls", label: "Controls in place", type: "textarea" }, { name: "review_date", label: "Review by", type: "date", width: 6 },
            { name: "status", label: "Status", type: "select", width: 6, options: opts([["draft", "Draft"], ["active", "Active"], ["review_due", "Review due"], ["archived", "Archived"]]) }]} />}
        {tab === 3 && <ResourcePage embedded title="Inspection" url="/safety/inspections/" writePerm="ohs.manage" createLabel="Record inspection" searchable={false}
          defaults={{ date: new Date().toISOString().slice(0, 10), checklist: [{ item: "Fire exits clear and signed", ok: true, note: "" }, { item: "Extinguishers in date", ok: true, note: "" }, { item: "Sharps bins below fill line", ok: true, note: "" }, { item: "Floors dry / wet-floor signs used", ok: true, note: "" }, { item: "First-aid box stocked", ok: true, note: "" }] }}
          columns={[{ key: "date", label: "Date", render: (r) => fmtDate(r.date) }, { key: "title", label: "Inspection", render: (r) => <><b>{r.title}</b><br /><small>{r.department_name} · {r.inspector_name}</small></> },
            { key: "score", label: "Compliance", align: "right", render: (r) => (r.score == null ? "—" : `${r.score}%`) }, { key: "findings", label: "Findings", render: (r) => <small>{r.findings}</small> }]}
          rowActions={(r) => manage && <Button size="small" onClick={() => setInspecting(r)}>Add action</Button>}
          fields={[{ name: "title", label: "Title", required: true, width: 8 }, { name: "date", label: "Date", type: "date", required: true, width: 4 },
            { name: "department", label: "Department", type: "ref", ref: "/org/departments/" },
            { name: "checklist", label: "Checklist (JSON)", type: "json", helper: '[{"item": "...", "ok": true, "note": ""}]' }, { name: "findings", label: "Findings", type: "textarea" }]} />}
        {tab === 4 && <CardContent>
          <Alert severity="info" sx={{ mb: 1 }}>Fitness outcomes from occupational health. Clinical details are held separately by OH and are not shown here. Staff marked unfit cannot be rostered for clinical duties.</Alert>
          <DataTable dense rows={fitness.data || []} rowKey={(r) => r.employee} emptyTitle="Everyone assessed is fit for duty" columns={[
            { key: "name", label: "Employee" }, { key: "department", label: "Department" },
            { key: "label", label: "Status", render: (r) => <StatusChip value={r.status === "unfit" ? "error" : "warning"} label={r.label} /> },
            { key: "restrictions", label: "Restrictions" }, { key: "until", label: "Until", render: (r) => fmtDate(r.until) }]} />
        </CardContent>}
      </Card>
      <ReportIncidentDialog open={reporting} onClose={() => setReporting(false)} />
      <FormDialog open={!!inspecting} title={`Action from: ${inspecting?.title}`} onClose={() => setInspecting(null)}
        fields={[{ name: "description", label: "Action", type: "textarea", required: true }, { name: "owner", label: "Owner", type: "ref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name || u.username), width: 6 },
          { name: "due_date", label: "Due", type: "date", required: true, width: 6 }]}
        onSubmit={async (v) => { await api.post("/safety/actions/", { ...(v as R), inspection: inspecting?.id }); toast.ok("Action added."); inv("/safety/"); }} />
    </>
  );
}
