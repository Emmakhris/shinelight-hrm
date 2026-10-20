import { Grid2 as Grid, LinearProgress, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../api/hooks";
import { StatusChip } from "../../components/Feedback";
import { Kpi } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function Progress({ p }: { p: R }) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 140 }}>
      <LinearProgress variant="determinate" value={p.percent} sx={{ flex: 1, height: 8, borderRadius: 4 }}
        color={p.overdue ? "warning" : p.percent === 100 ? "success" : "primary"} />
      <small>{p.done}/{p.total}</small>
    </Stack>
  );
}

export default function Onboardings() {
  const nav = useNavigate();
  const [status, setStatus] = useState("in_progress");
  const dash = useApi<R>("/onboarding/records/dashboard/");
  const d = dash.data || {};
  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Onboarding in progress", d.active], ["Starting in 30 days", d.starting_next_30_days], ["Overdue tasks", d.overdue_tasks, d.overdue_tasks ? "#b45309" : undefined],
          ["Completed (90 days)", d.completed_90_days], ["Avg days to complete", d.avg_days_to_complete ?? "—"],
          ["Probation reviews due (30 days)", d.probation_due_30_days, undefined, () => nav("/onboarding/probation")]].map(([label, value, color, onClick]) => (
          <Grid key={label as string} size={{ xs: 6, md: 2 }}><Kpi label={label as string} value={(value ?? "—") as string} color={color as string} onClick={onClick as () => void} /></Grid>
        ))}
      </Grid>
      <ResourcePage title="Onboarding" url="/onboarding/records/" params={{ status }} writePerm="onboarding.manage" canEdit={false}
        subtitle="Checklists start automatically when a new employee is registered. Tasks route to HR, the manager, IT, finance, administration and the new hire."
        createLabel="Start onboarding" onRowClick={(r) => nav(`/onboarding/${r.id}`)}
        filters={<TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem><MenuItem value="in_progress">In progress</MenuItem><MenuItem value="completed">Completed</MenuItem><MenuItem value="cancelled">Cancelled</MenuItem>
        </TextField>}
        columns={[
          { key: "employee_name", label: "Employee", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.staff_number} · {r.job_title || "—"}</small></> },
          { key: "department_name", label: "Department", hideOnMobile: true },
          { key: "start_date", label: "Start date", render: (r) => fmtDate(r.start_date) },
          { key: "probation_end_date", label: "Probation ends", hideOnMobile: true, render: (r) => fmtDate(r.probation_end_date) },
          { key: "progress", label: "Progress", render: (r) => <Progress p={r.progress} /> },
          { key: "overdue", label: "Overdue", align: "right", render: (r) => r.progress.overdue || "" },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> },
        ]}
        fields={[
          { name: "employee", label: "Employee", type: "ref", ref: "/employees/", required: true },
          { name: "template", label: "Checklist (leave blank to pick automatically)", type: "ref", ref: "/onboarding/templates/" },
          { name: "start_date", label: "Start date (defaults to hire date)", type: "date", width: 6 },
          { name: "buddy", label: "Buddy", type: "ref", ref: "/directory/", width: 6 },
        ]}
      />
    </>
  );
}
