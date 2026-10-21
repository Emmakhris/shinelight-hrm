import { Alert, Button, Card, CardContent, Grid2 as Grid, MenuItem, Stack, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ChartTitle, Trend } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function Establishment() {
  const q = useApi<R>("/planning/establishment/");
  const d = q.data;
  if (!d) return <Loading />;
  const tot = d.departments.reduce((a: R, r: R) => ({ approved: a.approved + r.approved, occupied: a.occupied + r.occupied, vacant: a.vacant + r.vacant, budget: a.budget + r.budget, actual: a.actual + r.actual }),
    { approved: 0, occupied: 0, vacant: 0, budget: 0, actual: 0 });
  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Approved posts", tot.approved], ["Occupied", tot.occupied], ["Vacant", tot.vacant], ["Budget (annual)", fmtMoney(tot.budget)], ["Actual basic cost", fmtMoney(tot.actual)],
          ["Workforce mix", Object.entries(d.by_employment_type).map(([k, v]) => `${k} ${v}`).join(" · ")]].map(([l, v]) => <Grid key={l as string} size={{ xs: 6, md: 2 }}><Kpi label={l as string} value={v as string} /></Grid>)}
      </Grid>
      <Card sx={{ mb: 2 }}><DataTable dense rows={d.departments} rowKey={(r) => r.department} columns={[
        { key: "department", label: "Department" }, { key: "approved", label: "Approved", align: "right" }, { key: "occupied", label: "Occupied", align: "right" },
        { key: "vacant", label: "Vacant", align: "right" }, { key: "frozen", label: "Frozen", align: "right" }, { key: "proposed", label: "Proposed", align: "right" },
        { key: "budget", label: "Budget", align: "right", render: (r) => fmtMoney(r.budget) }, { key: "actual", label: "Actual (basic)", align: "right", render: (r) => fmtMoney(r.actual) },
        { key: "variance", label: "Variance", align: "right", render: (r) => <span style={{ color: r.variance < 0 ? "#b91c1c" : undefined }}>{fmtMoney(r.variance)}</span> }]} /></Card>
      {d.shortages && <Card><CardContent><ChartTitle>Skills shortages</ChartTitle>
        <DataTable dense rows={d.shortages.critical_roles_without_cover} rowKey={(r) => r.position} emptyTitle="Every critical role has ready cover" columns={[
          { key: "title", label: "Critical role without ready cover" }, { key: "department", label: "Department" }, { key: "flags", label: "Why", render: (r) => r.flags.join("; ") }]} />
        <DataTable dense rows={d.shortages.competency_gaps} rowKey={(r) => r.competency} emptyTitle="No competency gaps in the latest appraisals" columns={[
          { key: "competency", label: "Competency gap" }, { key: "people", label: "People", align: "right" }]} />
      </CardContent></Card>}
    </>
  );
}

export function PlanDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const plan = useApi<R>(`/planning/plans/${id}/`);
  const [scenario, setScenario] = useState<string>("");
  const proj = useApi<R>(`/planning/plans/${id}/project/`, { scenario: scenario || undefined });
  const [tab, setTab] = useState(0);
  const toast = useToast();
  const inv = useInvalidate();
  if (plan.isLoading) return <Loading />;
  const p = plan.data;
  if (!p) return <ErrorAlert error={plan.error} />;
  const r = proj.data;
  const editable = p.status !== "approved" && can("planning.manage");
  return (
    <>
      <PageHeader title={p.name} subtitle={`${p.year} · ${p.horizon_years}-year horizon`} crumbs={[{ label: "Workforce planning", to: "/planning" }, { label: p.name }]}
        actions={<><StatusChip value={p.status === "approved" ? "approved" : "draft"} label={p.status} />
          {p.status === "draft" && can("planning.manage") && <Button variant="contained" onClick={async () => { try { await post(`/planning/plans/${id}/submit/`); toast.ok("Submitted for HR Director and finance approval."); inv("/planning/"); } catch (e) { toast.error(e); } }}>Submit for approval</Button>}</>} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Projection" /><Tab label="Plan lines" /><Tab label="Scenarios" /></Tabs>
      {tab === 0 && <>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <TextField select size="small" label="Scenario" value={scenario} onChange={(e) => setScenario(e.target.value)} sx={{ minWidth: 240 }}>
            <MenuItem value="">Baseline (actual turnover, no growth)</MenuItem>{p.scenarios.map((s: R) => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
          </TextField>
        </Stack>
        {!r ? <Loading /> : <>
          <Alert severity="info" sx={{ mb: 2 }}>Attrition {r.attrition_percent.toFixed(1)}% a year · employer on-cost {r.on_cost_percent}% (from the statutory rate table) · costs are basic pay × 12 plus on-cost.</Alert>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Headcount: target vs projected</ChartTitle>
              <Trend data={r.years.map((y: R) => ({ month: `Year ${y.year}`, target: y.target, end: y.end }))} series={[{ key: "target", label: "Target" }, { key: "end", label: "Projected" }]} /></CardContent></Card></Grid>
            <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Annual staff cost (GHS)</ChartTitle>
              <Trend data={r.years.map((y: R) => ({ month: `Year ${y.year}`, cost: Number(y.cost) }))} series={[{ key: "cost", label: "Cost" }]} /></CardContent></Card></Grid>
          </Grid>
          {r.years.some((y: R) => y.over_budget) && <Alert severity="warning" sx={{ mb: 2 }}>Projected cost exceeds the scenario's budget cap in {r.years.filter((y: R) => y.over_budget).map((y: R) => `year ${y.year}`).join(", ")}.</Alert>}
          <Card sx={{ mb: 2 }}><DataTable dense rows={r.years} rowKey={(y) => y.year} columns={[{ key: "year", label: "Year", render: (y) => p.year + y.year - 1 },
            { key: "start", label: "Start", align: "right" }, { key: "retirements", label: "Retirements", align: "right" }, { key: "attrition", label: "Attrition", align: "right" },
            { key: "hires", label: "Hires needed", align: "right" }, { key: "target", label: "Target", align: "right" }, { key: "end", label: "End", align: "right" },
            { key: "cost", label: "Cost", align: "right", render: (y) => fmtMoney(y.cost) }]} /></Card>
          <Card sx={{ mb: 2 }}><DataTable dense rows={r.lines} rowKey={(l) => `${l.key}-${l.year}`} columns={[{ key: "label", label: "Line" }, { key: "year", label: "Yr", align: "right" },
            { key: "start", label: "Start", align: "right" }, { key: "hires", label: "Hires", align: "right" }, { key: "end", label: "End", align: "right" },
            { key: "gap", label: "Gap", align: "right", render: (l) => <span style={{ color: l.gap > 0 ? "#b45309" : undefined }}>{l.gap}</span> }, { key: "cost", label: "Cost", align: "right", render: (l) => fmtMoney(l.cost) }]} /></Card>
          {r.workload.length > 0 && <Card><CardContent><ChartTitle>Staff-to-workload</ChartTitle>
            <DataTable dense rows={r.workload} rowKey={(w) => w.label} columns={[{ key: "label", label: "Line" }, { key: "units", label: "Workload", align: "right", render: (w) => `${w.units} ${w.unit_label}` },
              { key: "current", label: "Staff now", align: "right" }, { key: "needed", label: "Needed at target ratio", align: "right" },
              { key: "shortfall", label: "Shortfall", align: "right", render: (w) => <b style={{ color: w.shortfall > 0 ? "#b91c1c" : undefined }}>{w.shortfall}</b> }]} /></CardContent></Card>}
        </>}
      </>}
      {tab === 1 && <Card><ResourcePage embedded title="Plan line" url="/planning/lines/" params={{ plan: id }} writePerm="planning.manage" canDelete={editable} canEdit={editable} canCreate={editable} searchable={false}
        createLabel="Add line" defaults={{ plan: Number(id) }}
        columns={[{ key: "department_name", label: "Department" }, { key: "job_title_name", label: "Role" }, { key: "employment_type", label: "Type" },
          { key: "planned_headcount", label: "Planned", align: "right" }, { key: "workload_units", label: "Workload", align: "right", render: (l) => (l.workload_units ? `${Number(l.workload_units)} ${l.workload_label}` : "—") }]}
        fields={[{ name: "plan", label: "Plan", type: "ref", ref: "/planning/plans/", disabled: true },
          { name: "department", label: "Department", type: "ref", ref: "/org/departments/", required: true, width: 6 }, { name: "job_title", label: "Role (blank = all)", type: "ref", ref: "/org/job-titles/", width: 6 },
          { name: "employment_type", label: "Employment type (blank = all)", type: "select", width: 6, options: [["permanent", "Permanent"], ["contract", "Fixed-term contract"], ["temporary", "Temporary"], ["national_service", "National Service"], ["casual", "Casual"]].map(([value, label]) => ({ value, label })) },
          { name: "planned_headcount", label: "Planned headcount", type: "number", required: true, width: 6 },
          { name: "workload_units", label: "Workload units (e.g. beds)", type: "number", width: 4 }, { name: "workload_label", label: "Unit name", width: 4 }, { name: "target_ratio", label: "Staff per unit", type: "number", width: 4 },
          { name: "justification", label: "Justification", type: "textarea" }]} /></Card>}
      {tab === 2 && <Card><ResourcePage embedded title="Scenario" url="/planning/scenarios/" params={{ plan: id }} writePerm="planning.manage" canDelete searchable={false} createLabel="Add scenario"
        defaults={{ plan: Number(id), salary_increase_percent: 10, growth_percent: 0, hiring_freeze: false, department_adjustments: {} }}
        columns={[{ key: "name", label: "Scenario" }, { key: "attrition_percent", label: "Attrition %", align: "right", render: (s) => (s.attrition_percent == null ? "actual" : Number(s.attrition_percent)) },
          { key: "salary_increase_percent", label: "Pay rise %", align: "right", render: (s) => Number(s.salary_increase_percent) }, { key: "growth_percent", label: "Growth %", align: "right", render: (s) => Number(s.growth_percent) },
          { key: "hiring_freeze", label: "Freeze", render: (s) => (s.hiring_freeze ? "Yes" : "") }, { key: "budget_cap", label: "Budget cap", align: "right", render: (s) => (Number(s.budget_cap) ? fmtMoney(s.budget_cap) : "—") }]}
        fields={[{ name: "plan", label: "Plan", type: "ref", ref: "/planning/plans/", disabled: true }, { name: "name", label: "Name", required: true },
          { name: "attrition_percent", label: "Attrition % (blank = last 12 months actual)", type: "number", width: 6 }, { name: "salary_increase_percent", label: "Annual pay rise %", type: "number", width: 6 },
          { name: "growth_percent", label: "Headcount growth % a year", type: "number", width: 6 }, { name: "budget_cap", label: "Annual budget cap (GHS)", type: "number", width: 6 },
          { name: "department_adjustments", label: "Department adjustments (JSON, % by department id)", type: "json", helper: '{"5": -10} cuts department 5 by 10%' },
          { name: "hiring_freeze", label: "Hiring freeze", type: "checkbox" }, { name: "notes", label: "Notes", type: "textarea" }]} /></Card>}
    </>
  );
}

export default function Planning() {
  const nav = useNavigate();
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Workforce planning" subtitle="Establishment and budget vs actual, workforce plans and what-if scenarios." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Establishment" /><Tab label="Workforce plans" /></Tabs>
      {tab === 0 && <Establishment />}
      {tab === 1 && <Card><ResourcePage embedded title="Plan" url="/planning/plans/" writePerm="planning.manage" canDelete searchable={false} createLabel="New plan"
        onRowClick={(r) => nav(`/planning/${r.id}`)} defaults={{ year: new Date().getFullYear() + 1, horizon_years: 3 }}
        columns={[{ key: "name", label: "Plan", render: (r) => <b>{r.name}</b> }, { key: "year", label: "Year" }, { key: "horizon_years", label: "Horizon (yrs)", align: "right" },
          { key: "lines", label: "Lines", align: "right", render: (r) => r.lines.length }, { key: "scenarios", label: "Scenarios", align: "right", render: (r) => r.scenarios.length },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "approved" ? "approved" : "draft"} label={r.status} /> }]}
        fields={[{ name: "name", label: "Name", required: true, width: 8 }, { name: "year", label: "Year", type: "number", required: true, width: 4 },
          { name: "horizon_years", label: "Horizon (years)", type: "number", width: 4 }, { name: "notes", label: "Notes", type: "textarea" }]} /></Card>}
    </>
  );
}
