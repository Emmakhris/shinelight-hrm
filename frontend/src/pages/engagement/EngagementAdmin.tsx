import { Alert, Box, Button, Card, CardContent, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { BarList, ChartTitle, Trend } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const TEMPLATE = [
  { key: "proud", text: "I am proud to work for this organization", type: "rating", dimension: "engagement" },
  { key: "recommend", text: "I would recommend this organization as a great place to work", type: "rating", dimension: "engagement" },
  { key: "manager", text: "My supervisor treats me with respect", type: "rating", dimension: "management" },
  { key: "workload", text: "My workload is manageable", type: "rating", dimension: "workload" },
  { key: "exhausted", text: "I rarely feel exhausted at the end of my shift", type: "rating", dimension: "burnout" },
  { key: "enps", text: "How likely are you to recommend us as an employer (0-10)?", type: "enps" },
  { key: "improve", text: "What one thing would most improve your work life?", type: "text", required: false },
];

export function Results({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useApi<R>(`/engagement/surveys/${id}/results/`);
  const d = q.data;
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Results — {d?.survey}</DialogTitle>
      <DialogContent>
        {!d ? <Loading /> : !d.sufficient ? <Alert severity="info">{d.responses} response(s) so far. Results appear once at least {d.min_group_size} people have responded, to protect anonymity.</Alert> : <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 4 }}><Kpi label="Responses" value={`${d.responses} / ${d.invited}`} hint={`${d.response_rate}% response rate`} /></Grid>
            <Grid size={{ xs: 4 }}><Kpi label="Engagement index" value={d.engagement_index == null ? "—" : `${d.engagement_index}% favourable`} /></Grid>
            <Grid size={{ xs: 4 }}><Kpi label="eNPS" value={d.questions.find((x: R) => x.type === "enps")?.enps ?? "—"} /></Grid>
          </Grid>
          <ChartTitle>Favourable by theme (% answering 4-5)</ChartTitle>
          <BarList data={Object.entries(d.dimensions as Record<string, R>).map(([k, v]) => ({ label: k, value: v.favourable }))} valueLabel="% favourable" />
          <DataTable dense rows={d.questions.filter((x: R) => x.type !== "text")} rowKey={(r) => r.key} columns={[{ key: "text", label: "Question" },
            { key: "average", label: "Average", align: "right", render: (r) => r.average ?? (r.enps != null ? `eNPS ${r.enps}` : "—") },
            { key: "favourable", label: "Favourable", align: "right", render: (r) => (r.favourable != null ? `${r.favourable}%` : "—") },
            { key: "unfavourable", label: "Unfavourable", align: "right", render: (r) => (r.unfavourable != null ? `${r.unfavourable}%` : "—") }]} />
          <Typography variant="subtitle2" sx={{ mt: 2 }}>By department (groups of {d.min_group_size}+ only)</Typography>
          <DataTable dense rows={d.departments} rowKey={(r) => r.department} emptyTitle="No group is large enough to show separately" columns={[
            { key: "department", label: "Department" }, { key: "responses", label: "Responses", align: "right" },
            ...Object.keys(d.dimensions).map((k) => ({ key: k, label: k, align: "right" as const, render: (r: R) => (r.dimensions[k] ? `${r.dimensions[k].favourable}%` : "—") })),
            { key: "risk", label: "Workload / burnout risk", render: (r) => (r.risk ? <StatusChip value="warning" label="High" /> : "") }]} />
          {d.questions.filter((x: R) => x.type === "text").map((x: R) => (
            <Box key={x.key} sx={{ mt: 2 }}><Typography variant="subtitle2">{x.text}</Typography>
              {x.comments.map((c: string, i: number) => <Typography key={i} variant="body2" sx={{ borderLeft: "3px solid #e3e8ef", pl: 1, my: 0.5 }}>{c}</Typography>)}</Box>))}
        </>}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}

export default function EngagementAdmin() {
  const [tab, setTab] = useState(0);
  const [results, setResults] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState<R | null>(null);
  const overview = useApi<R>("/engagement/overview/");
  const toast = useToast();
  const inv = useInvalidate();
  const o = overview.data;
  return (
    <>
      <PageHeader title="Engagement administration" subtitle="Surveys and results, action plans, suggestions and staff events." />
      {(o?.trends?.length ?? 0) > 0 && o && <Card sx={{ mb: 2 }}><CardContent><ChartTitle>Engagement index over time (% favourable)</ChartTitle>
        <Trend data={o.trends.map((t: R) => ({ month: t.survey, engagement: t.engagement_index }))} series={[{ key: "engagement", label: "Engagement index" }]} /></CardContent></Card>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Surveys" /><Tab label="Action plans" /><Tab label="Suggestions" /><Tab label="Events" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Survey" url="/engagement/surveys/" writePerm="engagement.manage" canDelete createLabel="New survey"
          defaults={{ kind: "pulse", anonymous: true, min_group_size: 5, questions: TEMPLATE, departments: [] }}
          columns={[{ key: "title", label: "Survey", render: (r) => <><b>{r.title}</b><br /><small>{r.kind}{r.anonymous ? " · anonymous" : ""}</small></> },
            { key: "participation", label: "Responded", align: "right", render: (r) => `${r.participation.responded}/${r.participation.invited}` },
            { key: "closes_on", label: "Closes", render: (r) => fmtDate(r.closes_on) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "open" ? "in_progress" : r.status === "closed" ? "completed" : "draft"} label={r.status} /> }]}
          rowActions={(r) => <>
            {r.status === "draft" && <Button size="small" variant="contained" onClick={async () => { const x = await post<R>(`/engagement/surveys/${r.id}/launch/`); toast.ok(`Sent to ${x.invited} staff.`); inv("/engagement/"); }}>Launch</Button>}
            {r.status === "open" && <Button size="small" onClick={async () => { await post(`/engagement/surveys/${r.id}/close/`); inv("/engagement/"); }}>Close</Button>}
            {r.status !== "draft" && <Button size="small" onClick={() => setResults(r.id)}>Results</Button>}</>}
          fields={[{ name: "title", label: "Title", required: true, width: 8 },
            { name: "kind", label: "Type", type: "select", width: 4, options: [["engagement", "Engagement survey"], ["pulse", "Pulse survey"], ["stay", "Stay interview"], ["wellbeing", "Wellbeing check"], ["other", "Other"]].map(([value, label]) => ({ value, label })) },
            { name: "intro", label: "Introduction", type: "textarea" },
            { name: "departments", label: "Departments (blank = everyone)", type: "multiref", ref: "/org/departments/" },
            { name: "closes_on", label: "Closes on", type: "date", width: 4 }, { name: "min_group_size", label: "Minimum group size for results", type: "number", width: 4 },
            { name: "anonymous", label: "Anonymous", type: "checkbox", width: 4 },
            { name: "questions", label: "Questions (JSON)", type: "json", helper: 'types: rating (1-5), enps (0-10), text, choice; dimension groups ratings into themes (engagement, workload, burnout...)' }]} />}
        {tab === 1 && <ResourcePage embedded title="Action" url="/engagement/action-plans/" writePerm="engagement.manage" canDelete searchable={false} createLabel="Add action"
          defaults={{ status: "planned" }}
          columns={[{ key: "issue", label: "Issue raised", render: (r) => <><b>{r.issue}</b><br /><small>{r.survey_title} · {r.department_name}</small></> },
            { key: "action", label: "Action" }, { key: "owner_name", label: "Owner" }, { key: "due_date", label: "Due", render: (r) => fmtDate(r.due_date) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "done" ? "completed" : r.status === "planned" ? "pending" : "in_progress"} label={r.status} /> }]}
          fields={[{ name: "survey", label: "Survey", type: "ref", ref: "/engagement/surveys/", refLabel: (s) => String(s.title), width: 6 },
            { name: "department", label: "Department", type: "ref", ref: "/org/departments/", width: 6 },
            { name: "issue", label: "Issue raised by staff", required: true }, { name: "action", label: "What we will do", type: "textarea", required: true },
            { name: "owner", label: "Owner", type: "ref", ref: "/directory/", width: 4 }, { name: "due_date", label: "Due", type: "date", width: 4 },
            { name: "status", label: "Status", type: "select", width: 4, options: [["planned", "Planned"], ["in_progress", "In progress"], ["done", "Done"]].map(([value, label]) => ({ value, label })) },
            { name: "progress_note", label: "Progress", type: "textarea" }]} />}
        {tab === 2 && <ResourcePage embedded title="Suggestion" url="/engagement/suggestions/" canCreate={false} canEdit={false}
          columns={[{ key: "title", label: "Idea", render: (r) => <><b>{r.title}</b><br /><small>{r.text}</small></> }, { key: "category_label", label: "Area" },
            { key: "author_name", label: "From" }, { key: "vote_count", label: "Votes", align: "right" },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "implemented" ? "completed" : r.status === "declined" ? "rejected" : "pending"} label={r.status_label} /> }]}
          rowActions={(r) => <Button size="small" onClick={() => setReviewing(r)}>Respond</Button>} />}
        {tab === 3 && <ResourcePage embedded title="Event" url="/engagement/events/" writePerm="engagement.manage" canDelete searchable={false} createLabel="Add event"
          columns={[{ key: "title", label: "Event" }, { key: "kind", label: "Type" }, { key: "starts_at", label: "When", render: (r) => fmtDateTime(r.starts_at) },
            { key: "attendee_count", label: "Registered", align: "right", render: (r) => `${r.attendee_count}${r.capacity ? `/${r.capacity}` : ""}` }]}
          fields={[{ name: "title", label: "Title", required: true, width: 8 },
            { name: "kind", label: "Type", type: "select", width: 4, options: [["welfare", "Welfare"], ["wellness", "Wellness / health screening"], ["social", "Social / team"], ["eap", "Employee assistance (counselling)"], ["celebration", "Celebration"]].map(([value, label]) => ({ value, label })) },
            { name: "starts_at", label: "Date and time", type: "datetime", required: true, width: 6 }, { name: "location", label: "Location", width: 6 },
            { name: "capacity", label: "Capacity (optional)", type: "number", width: 6 }, { name: "description", label: "Description", type: "textarea" }]} />}
      </Card>
      {results && <Results id={results} onClose={() => setResults(null)} />}
      <FormDialog open={!!reviewing} title={`Respond: ${reviewing?.title}`} onClose={() => setReviewing(null)} initial={{ status: reviewing?.status, response: reviewing?.response }}
        fields={[{ name: "status", label: "Status", type: "select", required: true, options: [["new", "New"], ["under_review", "Under review"], ["accepted", "Accepted"], ["implemented", "Implemented"], ["declined", "Declined"]].map(([value, label]) => ({ value, label })) },
          { name: "response", label: "Response (visible to everyone)", type: "textarea" }]}
        onSubmit={async (v) => { await post(`/engagement/suggestions/${reviewing?.id}/review/`, v); toast.ok("Saved."); inv("/engagement/"); }} />
    </>
  );
}
