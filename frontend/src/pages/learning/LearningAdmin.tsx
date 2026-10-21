import { Alert, Button, Card, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Tab, Tabs,
  TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime, fmtMoney } from "../../utils";
import { ENROLL_STATUS_CHIP } from "./MyLearning";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const opts = (p: string[][]) => p.map(([value, label]) => ({ value, label }));
const CATEGORIES = opts([["clinical", "Clinical"], ["safety", "Health & safety"], ["compliance", "Compliance / policy"], ["leadership", "Leadership & management"],
  ["technical", "Technical / functional"], ["soft_skills", "Personal effectiveness"], ["induction", "Induction"]]);
const DELIVERY = opts([["classroom", "Classroom"], ["elearning", "E-learning"], ["external", "External programme"], ["on_the_job", "On-the-job"], ["blended", "Blended"]]);

function CourseContent({ course, onClose }: { course: R; onClose: () => void }) {
  const [tab, setTab] = useState(0);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{course.title}</DialogTitle>
      <DialogContent>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1 }}><Tab label="E-learning modules" /><Tab label="Assessment questions" /><Tab label="Sessions" /></Tabs>
        {tab === 0 && <ResourcePage embedded title="Module" url="/learning/modules/" params={{ course: course.id }} canDelete searchable={false} createLabel="Add module" defaults={{ course: course.id, kind: "text", order: 0, minutes: 10 }}
          columns={[{ key: "order", label: "#" }, { key: "title", label: "Module" }, { key: "kind", label: "Type" }, { key: "minutes", label: "Min", align: "right" }]}
          fields={[{ name: "course", label: "Course", type: "ref", ref: "/learning/courses/", refLabel: (c) => String(c.title), disabled: true },
            { name: "title", label: "Title", required: true, width: 8 }, { name: "order", label: "Order", type: "number", width: 4 },
            { name: "kind", label: "Type", type: "select", options: opts([["text", "Reading"], ["video", "Video"], ["document", "Document / slides"], ["link", "External link"]]), width: 6 },
            { name: "minutes", label: "Minutes", type: "number", width: 6 }, { name: "content", label: "Content", type: "textarea" }, { name: "url", label: "Video / resource URL" }]} />}
        {tab === 1 && <ResourcePage embedded title="Question" url="/learning/questions/" params={{ course: course.id }} canDelete searchable={false} createLabel="Add question"
          defaults={{ course: course.id, options: ["", ""], correct: [0], order: 0 }}
          columns={[{ key: "text", label: "Question" }, { key: "options", label: "Options", render: (q) => q.options.map((o: string, i: number) => (q.correct.includes(i) ? `✔ ${o}` : o)).join(" · ") }]}
          fields={[{ name: "course", label: "Course", type: "ref", ref: "/learning/courses/", refLabel: (c) => String(c.title), disabled: true },
            { name: "text", label: "Question", type: "textarea", required: true }, { name: "options", label: "Options (JSON list)", type: "json", required: true, helper: '["Water", "CO2", "Foam"]' },
            { name: "correct", label: "Correct option indexes (JSON, from 0)", type: "json", required: true, helper: "[1]" }, { name: "order", label: "Order", type: "number" }]} />}
        {tab === 2 && <Sessions course={course.id} />}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}

function Attendance({ session, onClose }: { session: R; onClose: () => void }) {
  const q = useApi<R[]>(`/learning/sessions/${session.id}/roster/`);
  const [rows, setRows] = useState<Record<number, R>>({});
  const toast = useToast();
  const inv = useInvalidate();
  const roster = q.data || [];
  const get = (r: R) => rows[r.enrollment] || { attended: true, score: "" };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Attendance — {session.course_title}, {fmtDateTime(session.start)}</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 1 }}>Attendees with a score at or above the pass mark (or no score) are completed; CPD credits and clinical competencies are recorded automatically.</Alert>
        <DataTable dense rows={roster} rowKey={(r) => r.enrollment} columns={[
          { key: "employee", label: "Participant", render: (r) => <>{r.employee}<br /><small>{r.staff_number} · {r.department}</small></> },
          { key: "status", label: "Status", render: (r) => <StatusChip value={ENROLL_STATUS_CHIP(r.status)} label={r.status} /> },
          { key: "att", label: "Attended", render: (r) => <Checkbox disabled={!["enrolled", "in_progress"].includes(r.status)} checked={!!get(r).attended} onChange={(e) => setRows({ ...rows, [r.enrollment]: { ...get(r), attended: e.target.checked } })} /> },
          { key: "score", label: "Score %", render: (r) => <TextField size="small" type="number" sx={{ width: 90 }} disabled={!["enrolled", "in_progress"].includes(r.status)} value={get(r).score}
            onChange={(e) => setRows({ ...rows, [r.enrollment]: { ...get(r), score: e.target.value } })} /> },
        ]} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" onClick={async () => {
          try {
            const body = roster.filter((r) => ["enrolled", "in_progress"].includes(r.status)).map((r) => ({ enrollment: r.enrollment, ...get(r), score: get(r).score === "" ? null : Number(get(r).score) }));
            const res = await post<R>(`/learning/sessions/${session.id}/attendance/`, { rows: body });
            toast.ok(`${res.recorded} recorded.`); inv("/learning/"); onClose();
          } catch (e) { toast.error(e); }
        }}>Save attendance</Button>
      </DialogActions>
    </Dialog>
  );
}

function Sessions({ course }: { course?: number }) {
  const [att, setAtt] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <ResourcePage embedded title="Session" url="/learning/sessions/" params={{ course }} canDelete searchable={false} createLabel="Schedule session"
        defaults={{ course, capacity: 20 }}
        columns={[{ key: "start", label: "When", render: (s) => fmtDateTime(s.start) }, ...(course ? [] : [{ key: "course_title", label: "Course" }]),
          { key: "venue", label: "Venue / trainer", render: (s) => <>{s.venue}<br /><small>{s.trainer}</small></> },
          { key: "booked", label: "Booked", align: "right" as const, render: (s) => `${s.booked}/${s.capacity}` },
          { key: "status", label: "Status", render: (s) => <StatusChip value={s.status} /> }]}
        rowActions={(s) => <>
          {s.status === "scheduled" && new Date(s.start) <= new Date() && <Button size="small" variant="contained" onClick={() => setAtt(s)}>Attendance</Button>}
          {s.status === "scheduled" && <Button size="small" color="error" onClick={async () => { await post(`/learning/sessions/${s.id}/cancel/`); toast.ok("Session cancelled; participants notified."); inv("/learning/"); }}>Cancel</Button>}
        </>}
        fields={[{ name: "course", label: "Course", type: "ref", ref: "/learning/courses/", refLabel: (c) => String(c.title), required: true, disabled: !!course },
          { name: "start", label: "Start", type: "datetime", required: true, width: 6 }, { name: "end", label: "End", type: "datetime", required: true, width: 6 },
          { name: "venue", label: "Venue", width: 6 }, { name: "trainer", label: "Trainer", width: 6 },
          { name: "capacity", label: "Capacity", type: "number", width: 4 }, { name: "registration_deadline", label: "Registration closes", type: "date", width: 4 },
          { name: "actual_cost", label: "Total cost (GHS)", type: "number", width: 4 }]} />
      {att && <Attendance session={att} onClose={() => setAtt(null)} />}
    </>
  );
}

function Assign({ course, onClose }: { course: R; onClose: () => void }) {
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <FormDialog open title={`Assign: ${course.title}`} onClose={onClose} initial={{ employees: [] }}
      intro={<Alert severity="info">Choose people or a whole department. Existing open enrolments are skipped.</Alert>}
      fields={[{ name: "employees", label: "Employees", type: "multiref", ref: "/employees/", refLabel: (e) => String(e.full_name) },
        { name: "department", label: "…or everyone in a department", type: "ref", ref: "/org/departments/" },
        { name: "due_date", label: "Complete by", type: "date" }]}
      onSubmit={async (d) => { const r = await post<R>(`/learning/courses/${course.id}/assign/`, d); toast.ok(`${r.assigned} assigned.`); inv("/learning/"); }} />
  );
}

export default function LearningAdmin() {
  const nav = useNavigate();
  const [tab, setTab] = useState(0);
  const [content, setContent] = useState<R | null>(null);
  const [assign, setAssign] = useState<R | null>(null);
  const [status, setStatus] = useState("pending");
  const year = new Date().getFullYear();
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Training administration" subtitle="Course catalogue, sessions and attendance, enrolments, budgets and CPD." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label="Courses" /><Tab label="Sessions" /><Tab label="Enrolments" /><Tab label={`Budgets ${year}`} /><Tab label="CPD verification" /><Tab label="CPD requirements" />
      </Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Course" url="/learning/courses/" writePerm="learning.manage" createLabel="New course"
          columns={[{ key: "title", label: "Course", render: (c) => <><b>{c.title}</b> <small>{c.code}</small><br /><small>{c.category_label} · {c.delivery_label}{c.provider && ` · ${c.provider}`}</small></> },
            { key: "is_mandatory", label: "Mandatory", render: (c) => (c.is_mandatory ? `Yes${c.refresher_months ? `, every ${c.refresher_months} mo` : ""}` : "") },
            { key: "cost_per_participant", label: "Cost", align: "right", render: (c) => (Number(c.cost_per_participant) ? fmtMoney(c.cost_per_participant) : "—") },
            { key: "content", label: "Content", hideOnMobile: true, render: (c) => `${c.module_count} modules, ${c.question_count} questions` },
            { key: "is_active", label: "Active", render: (c) => (c.is_active ? "Yes" : "No") }]}
          rowActions={(c) => <><Button size="small" onClick={() => setContent(c)}>Content</Button><Button size="small" onClick={() => setAssign(c)}>Assign</Button></>}
          fields={[{ name: "title", label: "Title", required: true, width: 8 }, { name: "code", label: "Code", width: 4 },
            { name: "category", label: "Category", type: "select", options: CATEGORIES, width: 4 }, { name: "delivery", label: "Delivery", type: "select", options: DELIVERY, width: 4 },
            { name: "provider", label: "Provider (blank = internal)", width: 4 }, { name: "description", label: "Description", type: "textarea" },
            { name: "objectives", label: "Learning outcomes", type: "textarea" },
            { name: "duration_hours", label: "Hours", type: "number", width: 3 }, { name: "cpd_credits", label: "CPD credits", type: "number", width: 3 },
            { name: "cost_per_participant", label: "Cost / participant", type: "number", width: 3 }, { name: "pass_mark", label: "Pass mark %", type: "number", width: 3 },
            { name: "is_mandatory", label: "Mandatory", type: "checkbox", width: 4 }, { name: "applies_to_all", label: "…for every employee", type: "checkbox", width: 4 },
            { name: "refresher_months", label: "Refresher every (months)", type: "number", width: 4 },
            { name: "job_titles", label: "Mandatory for job titles", type: "multiref", ref: "/org/job-titles/" },
            { name: "competency_requirement", label: "Renews clinical competency", type: "ref", ref: "/hospital/competency-requirements/", width: 6 },
            { name: "competencies", label: "Develops competencies", type: "multiref", ref: "/performance/competencies/", width: 6 },
            { name: "self_enrol", label: "Employees can request it", type: "checkbox", width: 6 }, { name: "is_active", label: "Active", type: "checkbox", width: 6 }]}
          defaults={{ category: "technical", delivery: "classroom", duration_hours: 1, cpd_credits: 0, cost_per_participant: 0, pass_mark: 70, self_enrol: true, is_active: true, job_titles: [], competencies: [] }} />}
        {tab === 1 && <Sessions />}
        {tab === 2 && <ResourcePage embedded title="Enrolment" url="/learning/enrollments/" params={{ status }} canCreate={false} canEdit={false} onRowClick={(r) => nav(`/learning/enrollments/${r.id}`)}
          filters={<TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 170 }}>
            <MenuItem value="">All</MenuItem>{["pending", "enrolled", "waitlisted", "in_progress", "completed", "failed", "no_show", "rejected", "cancelled"].map((s) => <MenuItem key={s} value={s}>{s.replace("_", " ")}</MenuItem>)}
          </TextField>}
          columns={[{ key: "employee_name", label: "Employee", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.department_name}</small></> },
            { key: "course_title", label: "Course" }, { key: "source", label: "Source" },
            { key: "cost", label: "Cost", align: "right", render: (r) => (Number(r.cost) ? fmtMoney(r.cost) : "—") },
            { key: "due_date", label: "Due / completed", render: (r) => fmtDate(r.completed_at || r.due_date) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={ENROLL_STATUS_CHIP(r.status)} label={r.status_label} /> }]} />}
        {tab === 3 && <ResourcePage embedded title="Budget" url="/learning/budgets/" params={{ year }} canDelete searchable={false} defaults={{ year }}
          columns={[{ key: "department_name", label: "Department" }, { key: "amount", label: "Budget", align: "right", render: (b) => fmtMoney(b.amount) },
            { key: "committed", label: "Committed", align: "right", render: (b) => fmtMoney(b.status?.committed) },
            { key: "pending", label: "Pending approval", align: "right", render: (b) => fmtMoney(b.status?.pending) },
            { key: "available", label: "Available", align: "right", render: (b) => fmtMoney(b.status?.available) }]}
          fields={[{ name: "department", label: "Department", type: "ref", ref: "/org/departments/", required: true }, { name: "year", label: "Year", type: "number", width: 6 },
            { name: "amount", label: "Amount (GHS)", type: "number", required: true, width: 6 }]} />}
        {tab === 4 && <ResourcePage embedded title="CPD record" url="/learning/cpd/" params={{ status: "pending" }} canCreate={false} canEdit={false} searchable={false}
          columns={[{ key: "employee_name", label: "Employee" }, { key: "title", label: "Activity", render: (r) => <>{r.title}<br /><small>{r.provider} · {r.category}</small></> },
            { key: "activity_date", label: "Date", render: (r) => fmtDate(r.activity_date) }, { key: "credits", label: "Credits", align: "right", render: (r) => Number(r.credits) }]}
          rowActions={(r) => <><Button size="small" variant="contained" onClick={async () => { await post(`/learning/cpd/${r.id}/verify/`, { approve: true }); toast.ok("Verified."); inv("/learning/"); }}>Verify</Button>
            <Button size="small" color="error" onClick={async () => { await post(`/learning/cpd/${r.id}/verify/`, { approve: false }); toast.ok("Rejected."); inv("/learning/"); }}>Reject</Button></>} />}
        {tab === 5 && <ResourcePage embedded title="CPD requirement" url="/learning/cpd-requirements/" canDelete searchable={false}
          columns={[{ key: "name", label: "Requirement" }, { key: "credits_per_year", label: "Credits / year", align: "right", render: (r) => Number(r.credits_per_year) },
            { key: "job_titles", label: "Job titles", align: "right", render: (r) => r.job_titles.length }]}
          fields={[{ name: "name", label: "Name (e.g. NMC renewal)", required: true }, { name: "credits_per_year", label: "Credits per year", type: "number", required: true },
            { name: "job_titles", label: "Applies to job titles", type: "multiref", ref: "/org/job-titles/", required: true }]} defaults={{ job_titles: [] }} />}
      </Card>
      {content && <CourseContent course={content} onClose={() => setContent(null)} />}
      {assign && <Assign course={assign} onClose={() => setAssign(null)} />}
    </>
  );
}
