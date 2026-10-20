import { Alert, FormControlLabel, List, ListItem, ListItemText, Switch } from "@mui/material";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { StatusChip } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { Progress } from "./Onboardings";
import { TaskList } from "./TaskList";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MyTasks() {
  const { me, can } = useAuth();
  const [open, setOpen] = useState(true);
  const mine = useApi<R | null>(me?.employee ? "/me/onboarding/" : null);
  const tasks = useApi<R>("/onboarding/tasks/", { mine: 1, open: open ? 1 : undefined, page_size: 200 });
  const own = mine.data;
  const others = (tasks.data?.results || []).filter((t: R) => t.employee_id !== me?.employee?.id);
  return (
    <>
      <PageHeader title="Onboarding tasks" subtitle="Tasks assigned to you for new employees, and your own onboarding if you have just joined." />
      {own && own.onboarding.status === "in_progress" && (
        <Section title={`Welcome, ${me?.employee?.full_name?.split(" ")[0]}! Your onboarding`}>
          <Alert severity="info" sx={{ mb: 2 }}>You started on {fmtDate(own.onboarding.start_date)}.
            {own.onboarding.buddy_name && <> Your buddy is <b>{own.onboarding.buddy_name}</b>.</>}
            {own.onboarding.probation_end_date && <> Your probation ends on {fmtDate(own.onboarding.probation_end_date)}.</>}</Alert>
          <Progress p={own.onboarding.progress} />
          <TaskList tasks={own.my_tasks} />
          {own.others.length > 0 && <List dense>
            {own.others.map((t: R, i: number) => <ListItem key={i} secondaryAction={<StatusChip value={t.status} />}>
              <ListItemText primary={t.title} secondary={`${t.owner} · due ${fmtDate(t.due_date)}`} /></ListItem>)}
          </List>}
        </Section>
      )}
      {(others.length > 0 || !own || !open) && (
        <Section title="Tasks for new employees" actions={<FormControlLabel control={<Switch checked={open} onChange={(e) => setOpen(e.target.checked)} />} label="Open only" />} dense>
          <TaskList tasks={others} loading={tasks.isLoading} showEmployee manage={can("onboarding.manage")} />
        </Section>
      )}
    </>
  );
}
