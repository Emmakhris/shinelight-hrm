import { Button, Card, Grid2 as Grid, Stack } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { OWNER_TYPES, TASK_CATEGORIES } from "../recruitment/constants";
import { Progress } from "./Onboardings";
import { TaskList } from "./TaskList";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function OnboardingDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const ob = useApi<R>(`/onboarding/records/${id}/`);
  const tasks = useApi<R[]>(`/onboarding/records/${id}/tasks/`);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  if (ob.isLoading) return <Loading />;
  if (!ob.data) return <ErrorAlert error={ob.error} />;
  const o = ob.data;
  const manage = can("onboarding.manage");
  const groups = TASK_CATEGORIES.map((c) => ({ ...c, tasks: (tasks.data || []).filter((t) => t.category === c.value) })).filter((g) => g.tasks.length);
  return (
    <>
      <PageHeader title={`Onboarding: ${o.employee_name}`} subtitle={`${o.staff_number} · ${o.job_title || ""} · ${o.department_name || ""}`}
        crumbs={[{ label: "Onboarding", to: "/onboarding" }, { label: o.employee_name }]}
        actions={<>
          <StatusChip value={o.status} />
          <Button component={RouterLink} to={`/employees/${o.employee}`}>Employee record</Button>
          {manage && o.status === "in_progress" && <><Button onClick={() => setEditing(true)}>Buddy</Button>
            <Button onClick={() => setAdding(true)}>Add task</Button>
            <Button color="error" onClick={() => setCancelling(true)}>Cancel</Button></>}
        </>} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 3 }}>
          <Card sx={{ p: 2 }}>
            <Stack spacing={1.5}>
              <Progress p={o.progress} />
              <Field label="Start date" value={fmtDate(o.start_date)} />
              <Field label="Checklist" value={o.template_name || "—"} />
              <Field label="Supervisor" value={o.supervisor_name || "—"} />
              <Field label="Buddy" value={o.buddy_name || "—"} />
              <Field label="Probation ends" value={fmtDate(o.probation_end_date)} />
              {o.completed_at && <Field label="Completed" value={fmtDate(o.completed_at)} />}
            </Stack>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          {groups.map((g) => <Section key={g.value} title={g.label} dense><TaskList tasks={g.tasks} manage={manage} /></Section>)}
          {!tasks.isLoading && groups.length === 0 && <Card sx={{ p: 2 }}>No tasks.</Card>}
        </Grid>
      </Grid>
      <FormDialog open={adding} title="Add task" onClose={() => setAdding(false)} initial={{ category: "other", owner_type: "hr", is_mandatory: true }}
        fields={[{ name: "title", label: "Task", required: true }, { name: "description", label: "Details", type: "textarea" },
          { name: "category", label: "Category", type: "select", options: TASK_CATEGORIES, width: 6 },
          { name: "owner_type", label: "Owner", type: "select", options: OWNER_TYPES, width: 6 },
          { name: "due_date", label: "Due", type: "date", required: true, width: 6 },
          { name: "is_mandatory", label: "Mandatory", type: "checkbox", width: 6 }]}
        onSubmit={async (d) => { await post(`/onboarding/records/${id}/add-task/`, d); toast.ok("Task added."); inv("/onboarding/"); }} />
      <FormDialog open={editing} title="Assign a buddy" onClose={() => setEditing(false)} initial={{ buddy: o.buddy }}
        fields={[{ name: "buddy", label: "Buddy", type: "ref", ref: "/directory/" }]}
        onSubmit={async (d) => { await api.patch(`/onboarding/records/${id}/`, d); toast.ok("Saved."); inv("/onboarding/"); }} />
      <ConfirmDialog open={cancelling} title="Cancel this onboarding?" color="error" confirmLabel="Cancel onboarding" onClose={() => setCancelling(false)}
        message="Use this when the new hire did not start. Open tasks stop appearing in task lists."
        onConfirm={async () => { await post(`/onboarding/records/${id}/cancel/`); toast.ok("Cancelled."); inv("/onboarding/"); }} />
    </>
  );
}
