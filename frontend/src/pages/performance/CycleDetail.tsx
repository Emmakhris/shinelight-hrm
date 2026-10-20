import { Alert, Button, Card, CardContent, Grid2 as Grid, MenuItem, Stack, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { BarList, ChartTitle } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";
import { CYCLE_FIELDS } from "./Cycles";
import { APPRAISAL_STATUS, CYCLE_STATUS } from "./common";
import { AppraisalTable } from "./MyPerformance";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const NEXT: Record<string, string> = { draft: "Launch", goal_setting: "Start mid-year phase", in_progress: "Open year-end reviews",
  review: "Move to calibration", calibration: "Release ratings and close" };

export default function CycleDetail() {
  const { id } = useParams();
  const toast = useToast();
  const inv = useInvalidate();
  const cycle = useApi<R>(`/performance/cycles/${id}/`);
  const summary = useApi<R>(`/performance/cycles/${id}/summary/`);
  const [tab, setTab] = useState(0);
  const [status, setStatus] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [editing, setEditing] = useState(false);
  const aps = useApi<R>("/performance/appraisals/", { cycle: id, status, page_size: 500 });
  if (cycle.isLoading) return <Loading />;
  if (!cycle.data) return <ErrorAlert error={cycle.error} />;
  const c = cycle.data;
  const s = summary.data || {};
  const refresh = () => inv("/performance/");
  return (
    <>
      <PageHeader title={c.name} subtitle={`${fmtDate(c.period_start)} – ${fmtDate(c.period_end)}`}
        crumbs={[{ label: "Review cycles", to: "/performance/cycles" }, { label: c.name }]}
        actions={<>
          <StatusChip value={c.status === "closed" ? "completed" : "in_progress"} label={CYCLE_STATUS[c.status]} />
          {c.status !== "closed" && <Button onClick={() => setEditing(true)}>Edit</Button>}
          {NEXT[c.status] && <Button variant="contained" onClick={() => setConfirm(true)}>{NEXT[c.status]}</Button>}
        </>} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Appraisals", s.appraisals], ["Rated", s.rated], ["Completed", s.by_status?.completed || 0], ["Ratings changed in calibration", s.calibrated_changes],
          ["Disputed by employee", s.disputed], ["Low ratings without a plan", s.low_ratings_without_plan]].map(([l, v]) => (
          <Grid key={l as string} size={{ xs: 6, md: 2 }}><Kpi label={l as string} value={(v ?? "—") as string} color={l === "Low ratings without a plan" && v ? "#b45309" : undefined} /></Grid>
        ))}
      </Grid>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Appraisals" /><Tab label="Rating distribution" /><Tab label="Goals" /></Tabs>
      {tab === 0 && <Card>
        <Stack direction="row" sx={{ p: 1.5 }} spacing={1}>
          <TextField select size="small" label="Stage" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 220 }}>
            <MenuItem value="">All</MenuItem>{Object.entries(APPRAISAL_STATUS).map(([k, v]) => <MenuItem key={k} value={k}>{v} ({s.by_status?.[k] || 0})</MenuItem>)}
          </TextField>
        </Stack>
        {c.status === "calibration" && <Alert severity="info" sx={{ mx: 1.5, mb: 1 }}>Open an appraisal in Calibration to confirm or adjust its rating. Releasing makes final ratings visible to employees.</Alert>}
        <AppraisalTable rows={aps.data?.results || []} loading={aps.isLoading} showEmployee />
      </Card>}
      {tab === 1 && <Card><CardContent>
        <ChartTitle>Final ratings</ChartTitle>
        <BarList data={(s.distribution || []).map((d: R) => ({ label: `${d.rating} – ${d.label}`, value: d.count }))} valueLabel="Employees" />
        <DataTable dense rows={s.distribution || []} rowKey={(r) => r.rating} columns={[{ key: "label", label: "Rating", render: (r) => `${r.rating} – ${r.label}` },
          { key: "count", label: "Employees", align: "right" }, { key: "percent", label: "Actual %", align: "right", render: (r) => `${r.percent}%` },
          { key: "target_percent", label: "Target %", align: "right", render: (r) => (r.target_percent == null ? "—" : `${r.target_percent}%`) }]} />
      </CardContent></Card>}
      {tab === 2 && <Card><ResourcePage embedded title="Goal" url="/performance/goals/" params={{ cycle: id }} writePerm="performance.manage" canDelete searchable={false}
        createLabel="Add goal" defaults={{ cycle: Number(id) }}
        columns={[{ key: "title", label: "Goal", render: (g) => <><b>{g.title}</b>{g.parent_title && <><br /><small>↳ supports {g.parent_title}</small></>}</> },
          { key: "department_name", label: "Level" }, { key: "measure", label: "Measure / target", render: (g) => `${g.measure}${g.target ? ` · ${g.target}` : ""}` },
          { key: "aligned_objectives", label: "Aligned objectives", align: "right" }]}
        fields={[{ name: "cycle", label: "Cycle", type: "ref", ref: "/performance/cycles/", disabled: true },
          { name: "title", label: "Goal", required: true }, { name: "description", label: "Description", type: "textarea" },
          { name: "department", label: "Department (blank = organization-wide)", type: "ref", ref: "/org/departments/", width: 6 },
          { name: "parent", label: "Supports goal", type: "ref", ref: "/performance/goals/", refParams: { cycle: Number(id) }, refLabel: (g) => String(g.title), width: 6 },
          { name: "measure", label: "Measure", width: 6 }, { name: "target", label: "Target", width: 6 },
          { name: "owner", label: "Owner", type: "ref", ref: "/directory/" }]} /></Card>}
      <ConfirmDialog open={confirm} title={`${NEXT[c.status]}?`} confirmLabel={NEXT[c.status]} onClose={() => setConfirm(false)}
        message={c.status === "draft" ? "Creates an appraisal for every eligible employee using the matching form, assigns their supervisor as reviewer and asks them to set objectives."
          : c.status === "in_progress" ? "Appraisals with agreed objectives open for self-assessment. Others stay behind until their objectives are agreed."
          : c.status === "calibration" ? "Final ratings are released to employees for acknowledgment and the cycle closes." : "Moves the cycle to its next phase."}
        onConfirm={async () => {
          const r = await post<R>(`/performance/cycles/${id}/${c.status === "draft" ? "launch" : "advance"}/`);
          toast.ok(c.status === "draft" ? `${r.created} appraisals created.${r.skipped_no_template?.length ? ` ${r.skipped_no_template.length} without a matching form.` : ""}` : `Now: ${CYCLE_STATUS[r.to] || r.to}`);
          refresh();
        }} />
      <FormDialog open={editing} title="Edit cycle" fields={CYCLE_FIELDS} initial={c} maxWidth="md" onClose={() => setEditing(false)}
        onSubmit={async (d) => { await api.patch(`/performance/cycles/${id}/`, d); toast.ok("Saved."); refresh(); }} />
    </>
  );
}
