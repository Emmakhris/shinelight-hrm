import { Alert, Box, Button, Card, CardContent, Chip, Grid2 as Grid, Tab, Tabs, Tooltip, Typography } from "@mui/material";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { BarList, ChartTitle } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading } from "../../components/Feedback";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const CELL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  current: { label: "✔", color: "success" }, expiring: { label: "Due", color: "warning" }, expired: { label: "Expired", color: "error" },
  missing: { label: "Missing", color: "error" },
};

function Matrix() {
  const q = useApi<R>("/learning/compliance/");
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const d = q.data;
  return (
    <Card>
      <Box sx={{ p: 2 }}><Typography>Overall compliance: <b>{d.compliance_percent ?? "—"}%</b> of required training current.</Typography></Box>
      <Box sx={{ overflowX: "auto" }}>
        <DataTable dense rows={d.rows} rowKey={(r) => r.employee} columns={[
          { key: "name", label: "Employee", render: (r) => <><b>{r.name}</b><br /><small>{r.job_title} · {r.department}</small></> },
          ...d.courses.map((c: R) => ({ key: String(c.id), label: c.title, align: "center" as const, render: (r: R) => {
            const cell = r.cells[String(c.id)];
            if (!cell) return <small>—</small>;
            const s = CELL[cell.status];
            return <Tooltip title={cell.expires_on ? `Valid to ${fmtDate(cell.expires_on)}` : ""}><Chip size="small" color={s.color} variant={cell.status === "current" ? "outlined" : "filled"} label={s.label} /></Tooltip>;
          } })),
        ]} />
      </Box>
    </Card>
  );
}

function Needs() {
  const q = useApi<R>("/learning/needs/");
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const d = q.data;
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 6 }}><Card><CardContent>
        <ChartTitle>Competency gaps (latest appraisals)</ChartTitle>
        <BarList data={d.competency_gaps.map((g: R) => ({ label: g.competency, value: g.people }))} valueLabel="People" />
        <DataTable dense rows={d.competency_gaps} rowKey={(r) => r.competency} columns={[{ key: "competency", label: "Competency" }, { key: "people", label: "People", align: "right" },
          { key: "courses", label: "Courses that address it", render: (g) => g.courses.map((c: R) => c.title).join(", ") || <small>No course linked — add one</small> }]} />
      </CardContent></Card></Grid>
      <Grid size={{ xs: 12, md: 6 }}><Card><CardContent>
        <ChartTitle>Mandatory training gaps</ChartTitle>
        <BarList data={d.mandatory_gaps.map((g: R) => ({ label: g.course, value: g.people }))} valueLabel="People" />
      </CardContent></Card></Grid>
      <Grid size={12}><Card><CardContent>
        <ChartTitle>Development needs recorded in appraisals</ChartTitle>
        <DataTable dense rows={d.development_needs} rowKey={(r) => r.employee} emptyTitle="None recorded" columns={[{ key: "name", label: "Employee" }, { key: "needs", label: "Needs" }]} />
      </CardContent></Card></Grid>
    </Grid>
  );
}

function Report() {
  const [year, setYear] = useState(new Date().getFullYear());
  const q = useApi<R>("/learning/report/", { year });
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const d = q.data;
  const stars = (v: number | null) => (v == null ? "—" : `${Number(v).toFixed(1)} / 5`);
  return (
    <>
      <Box sx={{ mb: 2 }}>{[year - 1, year].map((y) => <Button key={y} variant={y === year ? "contained" : "text"} onClick={() => setYear(y)}>{y}</Button>)}</Box>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Enrolments", d.enrolments], ["Completions", d.completions], ["Completion rate", d.completion_rate == null ? "—" : `${d.completion_rate}%`],
          ["Training hours", Number(d.training_hours)], ["Spend", fmtMoney(d.spend)], ["Cost per completion", d.cost_per_completion == null ? "—" : fmtMoney(d.cost_per_completion)],
          ["Participant rating", stars(d.avg_feedback)], ["Applied on the job", stars(d.avg_effectiveness)]].map(([l, v]) => (
          <Grid key={l as string} size={{ xs: 6, md: 3 }}><Kpi label={l as string} value={v as string} /></Grid>
        ))}
      </Grid>
      {d.pending_requests > 0 && <Alert severity="info" sx={{ mb: 2 }}>{d.pending_requests} training request(s) awaiting approval.</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Spend by department</ChartTitle>
          <DataTable dense rows={d.by_department} rowKey={(r) => r.department} columns={[{ key: "department", label: "Department" },
            { key: "spent", label: "Spent", align: "right", render: (r) => fmtMoney(r.spent) }, { key: "budget", label: "Budget", align: "right", render: (r) => (r.budget == null ? "—" : fmtMoney(r.budget)) },
            { key: "completions", label: "Completions", align: "right" }]} /></CardContent></Card></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Card><CardContent><ChartTitle>Effectiveness by course</ChartTitle>
          <DataTable dense rows={d.by_course} rowKey={(r) => r.course__title} columns={[{ key: "course__title", label: "Course" }, { key: "n", label: "Completed", align: "right" },
            { key: "feedback", label: "Rating", align: "right", render: (r) => stars(r.feedback) }, { key: "effectiveness", label: "Applied", align: "right", render: (r) => stars(r.effectiveness) }]} /></CardContent></Card></Grid>
      </Grid>
    </>
  );
}

export default function Compliance() {
  const { can } = useAuth();
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Training compliance & effectiveness" subtitle="Mandatory training status, skills gaps from appraisals, and training spend and impact." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Compliance matrix" />{can("learning.manage") && <Tab label="Training needs" />}{can("learning.manage") && <Tab label="Spend & effectiveness" />}</Tabs>
      {tab === 0 && <Matrix />}
      {tab === 1 && <Needs />}
      {tab === 2 && <Report />}
    </>
  );
}
