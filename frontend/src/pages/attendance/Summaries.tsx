import { Alert, Button, Card, Stack, TextField } from "@mui/material";
import dayjs from "dayjs";
import { useState } from "react";
import { post, useInvalidate } from "../../api/hooks";
import { ConfirmDialog, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

export default function Summaries() {
  const [start, setStart] = useState(dayjs().subtract(1, "month").startOf("month").format("YYYY-MM-DD"));
  const [end, setEnd] = useState(dayjs().subtract(1, "month").endOf("month").format("YYYY-MM-DD"));
  const [locking, setLocking] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  const build = async (lock: boolean) => {
    const r = await post<{ employees: number }>("/attendance/summaries/build/", { start, end, lock });
    toast.ok(`Summaries ${lock ? "built and locked" : "built"} for ${r.employees} employees.`); inv("/attendance/");
  };
  return (
    <>
      <PageHeader title="Attendance period summaries" subtitle="Monthly totals handed to payroll. Only approved overtime is counted." />
      <Alert severity="info" sx={{ mb: 2 }}>Build the summary before calculating payroll. Locking prevents further attendance changes for the period.</Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <TextField type="date" label="Period start" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
        <TextField type="date" label="Period end" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
        <Button variant="contained" onClick={() => build(false)}>Build / refresh</Button>
        <Button color="warning" onClick={() => setLocking(true)}>Build & lock</Button>
      </Stack>
      <Card><ResourcePage embedded title="Summary" url="/attendance/summaries/" params={{ period_start: start, period_end: end }}
        columns={[{ key: "staff_number", label: "Staff no" }, { key: "employee_name", label: "Name" },
          { key: "scheduled_days", label: "Scheduled", align: "right" }, { key: "days_present", label: "Present", align: "right" },
          { key: "days_absent", label: "Absent", align: "right" }, { key: "days_on_leave", label: "Leave", align: "right" },
          { key: "late_count", label: "Late", align: "right" }, { key: "incomplete_days", label: "Missing punch", align: "right" },
          { key: "ot_normal_hours", label: "OT weekday h", align: "right" }, { key: "ot_weekend_hours", label: "OT rest-day h", align: "right" },
          { key: "ot_holiday_hours", label: "OT holiday h", align: "right" }, { key: "night_shifts", label: "Nights", align: "right" },
          { key: "locked", label: "Locked", render: (r) => (r.locked ? "Yes" : "") }]} /></Card>
      <ConfirmDialog open={locking} onClose={() => setLocking(false)} title="Lock attendance for this period?" color="warning" confirmLabel="Build & lock"
        message="Locked days cannot be corrected or reprocessed." onConfirm={() => build(true)} />
    </>
  );
}
