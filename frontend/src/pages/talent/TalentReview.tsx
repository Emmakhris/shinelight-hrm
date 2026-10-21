import { Alert, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  Grid2 as Grid, MenuItem, Stack, Tab, Tabs, TextField, Tooltip, Typography } from "@mui/material";
import { useState } from "react";
import { errorMessage } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const READINESS = [["ready_now", "Ready now"], ["1_2_years", "Ready in 1-2 years"], ["3_plus", "Ready in 3+ years"], ["emergency", "Emergency cover only"]].map(([value, label]) => ({ value, label }));
// box order for display: top row = high potential
const LAYOUT = [3, 6, 9, 2, 5, 8, 1, 4, 7];
const BOX_COLOR: Record<number, string> = { 9: "#dcfce7", 8: "#ecfdf5", 6: "#ecfdf5", 7: "#f1f5f9", 5: "#f1f5f9", 3: "#fef9c3", 4: "#f1f5f9", 2: "#fef3c7", 1: "#fee2e2" };

function AssessDialog({ onClose }: { onClose: () => void }) {
  const criteria = useApi<R[]>("/talent/assessments/criteria/");
  const [emp, setEmp] = useState<R | null>(null);
  const [f, setF] = useState<R>({ period: `${new Date().getFullYear()} talent review`, performance: 2, potential: 2, rationale: "", flight_risk: "low" });
  const [c, setC] = useState<Record<string, R>>({});
  const [err, setErr] = useState<string | null>(null);
  const { can } = useAuth();
  const team = useApi<R>("/me/team/");
  const all = useApi<R>(can("talent.manage") ? "/employees/" : null, { page_size: 500, status: "active" });
  const people: R[] = can("talent.manage") ? (all.data?.results || []).map((e: R) => ({ id: e.id, name: e.full_name })) : team.data?.members || [];
  const detail = useApi<R>(emp ? `/talent/employees/${emp.id}/` : null);
  const inv = useInvalidate();
  const toast = useToast();
  const submit = async () => {
    setErr(null);
    try { await post("/talent/assessments/", { ...f, employee: emp?.id, criteria: c }); toast.ok("Assessment saved."); inv("/talent/"); onClose(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Talent assessment</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2 }}>Placements must be explained. Potential is your judgement against the published criteria, each backed by evidence — the system never labels anyone automatically.</Alert>
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select fullWidth label="Employee" value={emp?.id || ""} onChange={(e) => setEmp(people.find((p) => p.id === Number(e.target.value)) || null)}>
              {people.map((p) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
            </TextField>
            <TextField fullWidth label="Review period" value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })} />
          </Stack>
          {detail.data && <Alert severity="success">Suggested performance from the latest appraisal: <b>{detail.data.suggested_performance ?? "no rating yet"}</b> (1 below, 2 meets, 3 exceeds). {detail.data.profile?.aspirations && `Aspirations: ${detail.data.profile.aspirations}`}</Alert>}
          <Stack direction="row" spacing={2}>
            <TextField select fullWidth label="Performance" value={f.performance} onChange={(e) => setF({ ...f, performance: Number(e.target.value) })}>
              {[[1, "Below expectations"], [2, "Meets expectations"], [3, "Exceeds expectations"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField>
            <TextField select fullWidth label="Potential" value={f.potential} onChange={(e) => setF({ ...f, potential: Number(e.target.value) })}>
              {[[1, "Limited (well placed)"], [2, "Moderate (≥1 criterion)"], [3, "High (≥3 criteria)"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField>
            <TextField select fullWidth label="Flight risk" value={f.flight_risk} onChange={(e) => setF({ ...f, flight_risk: e.target.value })}>
              {["low", "medium", "high"].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}</TextField>
          </Stack>
          <Typography variant="subtitle2">Potential criteria</Typography>
          {(criteria.data || []).map((cr) => (
            <Stack key={cr.key} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
              <FormControlLabel sx={{ minWidth: 330 }} control={<Checkbox checked={!!c[cr.key]?.met} onChange={(e) => setC({ ...c, [cr.key]: { ...c[cr.key], met: e.target.checked } })} />} label={cr.label} />
              {c[cr.key]?.met && <TextField size="small" fullWidth label="Evidence" value={c[cr.key]?.evidence || ""} onChange={(e) => setC({ ...c, [cr.key]: { ...c[cr.key], evidence: e.target.value } })} />}
            </Stack>))}
          <TextField label="Rationale for this placement" multiline minRows={3} value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} />
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" disabled={!emp} onClick={submit}>Save</Button></DialogActions>
    </Dialog>
  );
}

function NineBox() {
  const [period, setPeriod] = useState("");
  const q = useApi<R>("/talent/assessments/grid/", { period: period || undefined });
  const d = q.data;
  const byBox: Record<number, R> = Object.fromEntries((d?.boxes || []).map((b: R) => [b.box, b]));
  return (
    <>
      {(d?.periods || []).length > 1 && <TextField select size="small" label="Period" value={d?.period || ""} onChange={(e) => setPeriod(e.target.value)} sx={{ mb: 2, minWidth: 220 }}>
        {(d?.periods || []).map((p: string) => <MenuItem key={p} value={p}>{p}</MenuItem>)}</TextField>}
      <Box sx={{ display: "grid", gridTemplateColumns: "28px repeat(3, 1fr)", gap: 1 }}>
        {LAYOUT.map((b, i) => (
          <Box key={b} sx={{ display: "contents" }}>
            {i % 3 === 0 && <Box sx={{ writingMode: "vertical-rl", transform: "rotate(180deg)", fontSize: 11, color: "text.secondary", textAlign: "center" }}>{["High", "Moderate", "Limited"][i / 3]} potential</Box>}
            <Card sx={{ bgcolor: BOX_COLOR[b], minHeight: 110 }} variant="outlined"><CardContent sx={{ p: 1.5 }}>
              <Typography variant="caption" fontWeight={600}>{byBox[b]?.label} ({byBox[b]?.count ?? 0})</Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                {(byBox[b]?.people || []).map((p: R) => <Tooltip key={p.assessment} title={`${p.job_title || ""} · ${p.department || ""} · flight risk ${p.flight_risk}`}>
                  <Chip size="small" label={p.name} color={p.flight_risk === "high" ? "warning" : "default"} /></Tooltip>)}
              </Stack>
            </CardContent></Card>
          </Box>))}
        <Box /><Typography variant="caption" align="center" color="text.secondary">Below</Typography><Typography variant="caption" align="center" color="text.secondary">Meets — performance</Typography><Typography variant="caption" align="center" color="text.secondary">Exceeds</Typography>
      </Box>
    </>
  );
}

function Succession() {
  const { can } = useAuth();
  const q = useApi<R>("/talent/succession/risk/");
  const [adding, setAdding] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const d = q.data;
  return (
    <>
      {d && <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Critical positions", d.critical_positions], ["Bench strength (ready-now cover)", d.bench_strength_percent == null ? "—" : `${d.bench_strength_percent}%`],
          ["Single-person dependencies", d.single_person_dependencies, "#b91c1c"], ["Retirement risks (2 yrs)", d.retirement_risks, "#b45309"]].map(([l, v, c]) => (
          <Grid key={l} size={{ xs: 6, md: 3 }}><Kpi label={l} value={v} color={v ? c : undefined} /></Grid>))}
      </Grid>}
      <Card><DataTable rows={d?.positions || []} rowKey={(r) => r.position} emptyTitle="Mark positions as critical (Organization → Positions) to plan succession" columns={[
        { key: "title", label: "Critical position", render: (r) => <><b>{r.title}</b> <small>{r.code}</small><br /><small>{r.department}</small></> },
        { key: "incumbents", label: "Incumbent", render: (r) => r.incumbents.map((i: R) => i.name).join(", ") || <i>Vacant</i> },
        { key: "successors", label: "Successors", render: (r) => r.successors.map((s: R) => <div key={s.id}><small>{s.name} — {s.readiness_label}</small></div>) },
        { key: "flags", label: "Risks", render: (r) => r.flags.map((f: string) => <Chip key={f} size="small" color={r.risk === "high" ? "error" : "warning"} variant="outlined" label={f} sx={{ m: 0.25 }} />) },
        { key: "risk", label: "", render: (r) => <StatusChip value={r.risk === "high" ? "error" : r.risk === "medium" ? "warning" : "active"} label={r.risk} /> },
        { key: "_a", label: "", render: (r) => can("talent.manage") && <Button size="small" onClick={() => setAdding(r)}>Add successor</Button> }]} /></Card>
      <FormDialog open={!!adding} title={`Successor for ${adding?.title}`} onClose={() => setAdding(null)} initial={{ readiness: "1_2_years", rank: 1 }}
        fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", required: true },
          { name: "readiness", label: "Readiness", type: "select", options: READINESS, required: true, width: 6 }, { name: "rank", label: "Rank", type: "number", width: 6 },
          { name: "development_actions", label: "Development actions to close the gap", type: "textarea" }]}
        onSubmit={async (v) => {
          let planId = adding?.plan;
          if (!planId) planId = (await post<R>("/talent/succession/", { position: adding?.position })).id;
          await post(`/talent/succession/${planId}/successors/`, v); toast.ok("Successor added."); inv("/talent/");
        }} />
    </>
  );
}

export default function TalentReview() {
  const [tab, setTab] = useState(0);
  const [assessing, setAssessing] = useState(false);
  return (
    <>
      <PageHeader title="Talent & succession" subtitle="Talent review (nine-box), succession cover for critical roles and career paths."
        actions={<Button variant="contained" onClick={() => setAssessing(true)}>Assess a team member</Button>} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Nine-box" /><Tab label="Succession" /><Tab label="Career paths" /></Tabs>
      {tab === 0 && <NineBox />}
      {tab === 1 && <Succession />}
      {tab === 2 && <Card><ResourcePage embedded title="Career path" url="/talent/career-paths/" writePerm="talent.manage" canDelete searchable={false} createLabel="Add path"
        defaults={{ min_years_in_role: 2, min_rating: 3, required_courses: [] }}
        columns={[{ key: "from_title_name", label: "From" }, { key: "to_title_name", label: "To" },
          { key: "min_years_in_role", label: "Years", align: "right", render: (r) => Number(r.min_years_in_role) }, { key: "min_rating", label: "Min rating", align: "right" },
          { key: "required_courses", label: "Courses", align: "right", render: (r) => r.required_courses.length }, { key: "required_qualification", label: "Qualification" }]}
        fields={[{ name: "from_title", label: "From role", type: "ref", ref: "/org/job-titles/", required: true, width: 6 }, { name: "to_title", label: "To role", type: "ref", ref: "/org/job-titles/", required: true, width: 6 },
          { name: "min_years_in_role", label: "Minimum years in role", type: "number", width: 6 }, { name: "min_rating", label: "Minimum latest rating", type: "number", width: 6 },
          { name: "required_courses", label: "Required courses", type: "multiref", ref: "/learning/courses/", refLabel: (c) => String(c.title) },
          { name: "required_qualification", label: "Required qualification" }, { name: "notes", label: "Notes", type: "textarea" }]} /></Card>}
      {assessing && <AssessDialog onClose={() => setAssessing(false)} />}
    </>
  );
}
