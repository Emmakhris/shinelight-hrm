import { Alert, Button, Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate, useList } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { EnrollmentTable, GoalsTable, RequestDialog } from "./MyLearning";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function TeamLearning() {
  const [tab, setTab] = useState(0);
  const [nominate, setNominate] = useState(false);
  const [pick, setPick] = useState<{ employee: number | ""; course: number | "" }>({ employee: "", course: "" });
  const [course, setCourse] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const teamQ = useApi<R>("/me/team/");
  const members: R[] = teamQ.data?.members || [];
  const courses = useList<R>("/learning/courses/");
  const en = useApi<R>("/learning/enrollments/", { team: 1, page_size: 300 });
  const rows = en.data?.results || [];
  const toEvaluate = rows.filter((r: R) => r.status === "completed" && !r.effectiveness_rating);
  const [mentoring, setMentoring] = useState(false);
  return (
    <>
      <PageHeader title="Team learning" subtitle="Your team's training, development plans and mentoring."
        actions={<><Button onClick={() => setMentoring(true)}>Set up mentoring</Button><Button variant="contained" onClick={() => setNominate(true)}>Nominate for training</Button></>} />
      {toEvaluate.length > 0 && <Alert severity="info" sx={{ mb: 2 }}>{toEvaluate.length} completed course(s) are waiting for your evaluation of how the training is being applied. Open them below.</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Training" /><Tab label="Development plans" /></Tabs>
      {tab === 0 && <Card><EnrollmentTable rows={rows} loading={en.isLoading} showEmployee /></Card>}
      {tab === 1 && <Card><GoalsTable params={{}} /></Card>}
      {nominate && !course && (
        <FormDialog open title="Nominate a team member" onClose={() => setNominate(false)} initial={pick}
          fields={[{ name: "employee", label: "Team member", type: "select", required: true, options: members.map((t) => ({ value: t.id as number, label: String(t.name) })) },
            { name: "course", label: "Course", type: "select", required: true, options: courses.items.map((c) => ({ value: c.id as number, label: String(c.title) })) }]}
          onSubmit={async (d) => { const v = d as R; setPick(v as typeof pick); setCourse(courses.items.find((c) => c.id === Number(v.course)) || null); }} />
      )}
      {course && <RequestDialog course={course} employee={Number(pick.employee)} onClose={() => { setCourse(null); setNominate(false); }} />}
      <FormDialog open={mentoring} title="Set up mentoring or coaching" onClose={() => setMentoring(false)} initial={{ kind: "mentoring", start_date: new Date().toISOString().slice(0, 10) }}
        fields={[{ name: "mentee", label: "Team member", type: "select", required: true, options: members.map((t) => ({ value: t.id as number, label: String(t.name) })) },
          { name: "mentor", label: "Mentor / coach", type: "ref", ref: "/directory/", required: true },
          { name: "kind", label: "Type", type: "select", options: [{ value: "mentoring", label: "Mentoring" }, { value: "coaching", label: "Coaching" }], width: 6 },
          { name: "start_date", label: "Start", type: "date", required: true, width: 6 },
          { name: "objectives", label: "Objectives", type: "textarea", required: true }]}
        onSubmit={async (d) => { await api.post("/learning/mentorships/", d); toast.ok("Mentoring set up."); inv("/learning/"); }} />
    </>
  );
}
