import { Alert, Box, Button, Card, CardActions, CardContent, Chip, Grid2 as Grid, Stack, Tab, Tabs, TextField,
  Typography } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime, fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export const ENROLL_STATUS_CHIP = (s: string) => (["enrolled", "in_progress"].includes(s) ? "in_progress" : s);

export function EnrollmentTable({ rows, loading, showEmployee }: { rows: R[]; loading?: boolean; showEmployee?: boolean }) {
  const nav = useNavigate();
  return (
    <DataTable dense loading={loading} rows={rows} onRowClick={(r) => nav(`/learning/enrollments/${r.id}`)} emptyTitle="No training yet"
      columns={[
        ...(showEmployee ? [{ key: "employee_name", label: "Employee", render: (r: R) => <><b>{r.employee_name}</b><br /><small>{r.department_name}</small></> }] : []),
        { key: "course_title", label: "Course", render: (r) => <><b>{r.course_title}</b>{r.source === "mandatory" && <Chip size="small" label="Mandatory" sx={{ ml: 1 }} />}</> },
        { key: "when", label: "When / due", render: (r) => (r.session_start ? fmtDateTime(r.session_start) : r.due_date ? `Due ${fmtDate(r.due_date)}` : "—") },
        { key: "status", label: "Status", render: (r) => <StatusChip value={ENROLL_STATUS_CHIP(r.status)} label={r.status_label} /> },
        { key: "completed_at", label: "Completed / valid to", hideOnMobile: true, render: (r) => (r.completed_at ? `${fmtDate(r.completed_at)}${r.expires_on ? ` → ${fmtDate(r.expires_on)}` : ""}` : "—") },
      ]} />
  );
}

export function RequestDialog({ course, employee, onClose }: { course: R | null; employee?: number; onClose: () => void }) {
  const toast = useToast();
  const inv = useInvalidate();
  if (!course) return null;
  const paid = Number(course.cost_per_participant) > 0 || course.delivery === "external";
  return (
    <FormDialog open title={`${employee ? "Nominate for" : "Request"}: ${course.title}`} onClose={onClose} initial={{ session: course.upcoming_sessions?.[0]?.id ?? null }}
      intro={paid ? <Alert severity="info">This training costs {fmtMoney(course.cost_per_participant)} and needs approval (supervisor and training office; HR Director above GHS 2,000 or beyond the budget).</Alert> : undefined}
      fields={[
        ...(course.upcoming_sessions?.length ? [{ name: "session", label: "Session", type: "select" as const, required: true,
          options: course.upcoming_sessions.map((s: R) => ({ value: s.id, label: `${fmtDateTime(s.start)} · ${s.venue || "TBC"} · ${s.seats_left > 0 ? `${s.seats_left} seats` : "waitlist"}` })) }] : []),
        { name: "reason", label: paid ? "How will this help in the role? (required)" : "Why are you taking this course? (optional)", type: "textarea" as const, required: paid },
      ]}
      onSubmit={async (d) => {
        const r = await api.post<R>("/learning/enrollments/", { ...(d as R), course: course.id, employee });
        toast.ok(r.data.status === "pending" ? "Request sent for approval." : r.data.status === "waitlisted" ? "Added to the waitlist." : "Enrolled.");
        inv("/learning/");
      }} />
  );
}

function Catalogue() {
  const [search, setSearch] = useState("");
  const q = useApi<R>("/learning/courses/", { search, page_size: 100 });
  const [req, setReq] = useState<R | null>(null);
  return (
    <>
      <TextField placeholder="Search courses…" value={search} onChange={(e) => setSearch(e.target.value)} sx={{ mb: 2, minWidth: 280 }} />
      <Grid container spacing={2}>
        {(q.data?.results || []).map((c: R) => (
          <Grid key={c.id} size={{ xs: 12, md: 6, lg: 4 }}>
            <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
              <CardContent sx={{ flex: 1 }}>
                <Typography variant="overline" color="text.secondary">{c.category_label} · {c.delivery_label}</Typography>
                <Typography variant="h6">{c.title}</Typography>
                <Stack direction="row" spacing={1} sx={{ my: 1 }} flexWrap="wrap" useFlexGap>
                  <Chip size="small" label={`${Number(c.duration_hours)} h`} />
                  {Number(c.cpd_credits) > 0 && <Chip size="small" color="primary" variant="outlined" label={`${Number(c.cpd_credits)} CPD`} />}
                  {c.is_mandatory && <Chip size="small" color="warning" variant="outlined" label="Mandatory" />}
                  {Number(c.cost_per_participant) > 0 && <Chip size="small" label={fmtMoney(c.cost_per_participant)} />}
                  {c.provider && <Chip size="small" label={c.provider} />}
                </Stack>
                <Typography variant="body2" color="text.secondary">{c.description}</Typography>
                {c.upcoming_sessions?.length > 0 && <Typography variant="caption" display="block" sx={{ mt: 1 }}>Next: {fmtDateTime(c.upcoming_sessions[0].start)}</Typography>}
              </CardContent>
              <CardActions>
                {c.my_enrollment && !["cancelled", "rejected"].includes(c.my_enrollment.status)
                  ? <Chip label={c.my_enrollment.status === "completed" ? `Completed ${fmtDate(c.my_enrollment.completed_at)}` : c.my_enrollment.status} color={c.my_enrollment.status === "completed" ? "success" : "default"} />
                  : c.self_enrol ? <Button variant="contained" onClick={() => setReq(c)}>{Number(c.cost_per_participant) > 0 || c.delivery === "external" ? "Request" : "Enrol"}</Button>
                  : <Typography variant="caption">By nomination</Typography>}
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>
      <RequestDialog course={req} onClose={() => setReq(null)} />
    </>
  );
}

function CPD() {
  const sum = useApi<R>("/learning/cpd/summary/");
  const s = sum.data;
  return (
    <>
      {s && <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 4 }}><Kpi label={`CPD credits ${s.year}`} value={Number(s.earned)} /></Grid>
        <Grid size={{ xs: 4 }}><Kpi label="Required" value={s.required != null ? Number(s.required) : "—"} hint={s.requirement} /></Grid>
        <Grid size={{ xs: 4 }}><Kpi label="Still needed" value={s.shortfall != null ? Number(s.shortfall) : "—"} color={Number(s.shortfall) > 0 ? "#b45309" : undefined} /></Grid>
      </Grid>}
      <Card><ResourcePage embedded title="CPD activity" url="/learning/cpd/" params={{ mine: 1 }} canEdit={false} canDelete searchable={false} createLabel="Log CPD activity"
        intro={<Alert severity="info">Activities you log are verified by the training office before they count. Courses completed here are added automatically.</Alert>}
        columns={[{ key: "activity_date", label: "Date", render: (r) => fmtDate(r.activity_date) }, { key: "title", label: "Activity", render: (r) => <>{r.title}<br /><small>{r.provider}</small></> },
          { key: "credits", label: "Credits", align: "right", render: (r) => Number(r.credits) }, { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]}
        fields={[{ name: "title", label: "Activity", required: true }, { name: "provider", label: "Provider", width: 6 },
          { name: "activity_date", label: "Date", type: "date", required: true, width: 3 }, { name: "credits", label: "Credits", type: "number", required: true, width: 3 },
          { name: "category", label: "Category (e.g. conference, journal club)" }]} /></Card>
    </>
  );
}

export function GoalsTable({ params, employee }: { params: R; employee?: number }) {
  return (
    <ResourcePage embedded title="Development goal" url="/learning/development-goals/" params={params} canDelete searchable={false} createLabel="Add goal"
      defaults={{ status: "planned", employee }}
      columns={[{ key: "title", label: "Goal", render: (g) => <><b>{g.title}</b>{employee === undefined && params.mine !== 1 && <><br /><small>{g.employee_name}</small></>}{g.competency_name && <><br /><small>Competency: {g.competency_name}</small></>}</> },
        { key: "actions", label: "Actions", render: (g) => <small>{g.actions}{g.courses?.length > 0 && <><br />Suggested: {g.courses.map((c: R) => c.title).join(", ")}</>}</small> },
        { key: "target_date", label: "Target", render: (g) => fmtDate(g.target_date) },
        { key: "status", label: "Status", render: (g) => <StatusChip value={g.status === "achieved" ? "completed" : g.status} label={g.status.replace("_", " ")} /> }]}
      fields={[{ name: "title", label: "Goal", required: true }, { name: "competency", label: "Competency", type: "ref", ref: "/performance/competencies/", width: 6 },
        { name: "target_date", label: "Target date", type: "date", width: 6 }, { name: "actions", label: "Actions (training, assignments, coaching)", type: "textarea" },
        { name: "status", label: "Status", type: "select", width: 6, options: [["planned", "Planned"], ["in_progress", "In progress"], ["achieved", "Achieved"], ["dropped", "Dropped"]].map(([value, label]) => ({ value, label })) },
        { name: "progress_notes", label: "Progress notes", type: "textarea" }]} />
  );
}

function Mentoring() {
  const q = useApi<R>("/learning/mentorships/");
  const [log, setLog] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      {(q.data?.results || []).length === 0 && <Card sx={{ p: 2 }}>No mentoring or coaching relationships. Your supervisor or HR can set one up.</Card>}
      {(q.data?.results || []).map((m: R) => (
        <Card key={m.id} sx={{ mb: 2 }}><CardContent>
          <Stack direction="row" justifyContent="space-between"><Typography variant="h6">{m.kind === "coaching" ? "Coaching" : "Mentoring"}: {m.mentor_name} → {m.mentee_name}</Typography><StatusChip value={m.status} /></Stack>
          <Typography variant="body2" sx={{ mb: 1 }}>{m.objectives}</Typography>
          {m.sessions.map((s: R) => <Box key={s.id} sx={{ borderTop: "1px solid #eef0f3", py: 0.5 }}><small><b>{fmtDate(s.date)}</b> — {s.notes}{s.next_steps && ` · Next: ${s.next_steps}`}</small></Box>)}
        </CardContent><CardActions>{m.status === "active" && <Button size="small" onClick={() => setLog(m)}>Log session</Button>}</CardActions></Card>
      ))}
      <FormDialog open={!!log} title="Log mentoring session" onClose={() => setLog(null)} initial={{ date: new Date().toISOString().slice(0, 10) }}
        fields={[{ name: "date", label: "Date", type: "date", required: true }, { name: "notes", label: "What was discussed", type: "textarea", required: true }, { name: "next_steps", label: "Next steps", type: "textarea" }]}
        onSubmit={async (d) => { await api.post(`/learning/mentorships/${log?.id}/log/`, d); toast.ok("Session logged."); inv("/learning/"); }} />
    </>
  );
}

export default function MyLearning() {
  const [tab, setTab] = useState(0);
  const q = useApi<R>("/learning/enrollments/", { mine: 1, page_size: 200 });
  const rows = q.data?.results || [];
  const todo = rows.filter((r: R) => ["enrolled", "in_progress"].includes(r.status));
  return (
    <>
      <PageHeader title="My learning" subtitle="Your training, the course catalogue, CPD credits and development plan." />
      {todo.some((r: R) => r.source === "mandatory") && <Alert severity="warning" sx={{ mb: 2 }}>You have mandatory training to complete.</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label={`My training (${todo.length} to do)`} /><Tab label="Course catalogue" /><Tab label="CPD" /><Tab label="Development plan" /><Tab label="Mentoring" />
      </Tabs>
      {tab === 0 && <Card><EnrollmentTable rows={rows} loading={q.isLoading} /></Card>}
      {tab === 1 && <Catalogue />}
      {tab === 2 && <CPD />}
      {tab === 3 && <Card><GoalsTable params={{ mine: 1 }} /></Card>}
      {tab === 4 && <Mentoring />}
    </>
  );
}
