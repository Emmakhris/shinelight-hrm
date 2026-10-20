import { Box, Button, Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { post, useInvalidate } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDateTime } from "../../utils";

const WEEKDAYS = "Weekday numbers: Mon=0 … Sun=6, e.g. [5, 6]";

export default function AttendanceSetup() {
  const [tab, setTab] = useState(0);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Shifts, policies & devices" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label="Shifts" /><Tab label="Attendance policies" /><Tab label="Rotation patterns" /><Tab label="Biometric devices" /><Tab label="Device enrolment" />
      </Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Shift" url="/attendance/shifts/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "start_time", label: "Start" }, { key: "end_time", label: "End" },
            { key: "break_minutes", label: "Break (min)" }, { key: "grace_in_minutes", label: "Grace (min)" },
            { key: "is_night", label: "Night", render: (r) => (r.is_night ? "Yes" : "") },
            { key: "color", label: "", render: (r) => <Box sx={{ width: 14, height: 14, borderRadius: 1, bgcolor: r.color as string }} /> }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "start_time", label: "Start", type: "time", required: true, width: 6 }, { name: "end_time", label: "End", type: "time", required: true, width: 6 },
            { name: "break_minutes", label: "Unpaid break (min)", type: "number", width: 4 }, { name: "grace_in_minutes", label: "Late grace (min)", type: "number", width: 4 },
            { name: "grace_out_minutes", label: "Early-leave grace (min)", type: "number", width: 4 },
            { name: "is_night", label: "Night duty", type: "checkbox", width: 4 }, { name: "is_on_call", label: "On-call shift", type: "checkbox", width: 4 },
            { name: "color", label: "Colour", type: "color", width: 4 }]} defaults={{ break_minutes: 60, grace_in_minutes: 15, grace_out_minutes: 10, color: "#0ea5e9" }} />}
        {tab === 1 && <ResourcePage embedded title="Policy" url="/attendance/policies/" canDelete
          columns={[{ key: "name", label: "Policy" }, { key: "priority", label: "Priority" }, { key: "overtime_after_minutes", label: "OT after (min)" },
            { key: "require_geofence", label: "Geofence", render: (r) => (r.require_geofence ? "Yes" : "") },
            { key: "absent_deduction", label: "Deduct absences", render: (r) => (r.absent_deduction ? "Yes" : "") }]}
          fields={[{ name: "name", label: "Name", required: true },
            { name: "department", label: "Department (blank = all)", type: "ref", ref: "/org/departments/", width: 4 },
            { name: "category", label: "Category", type: "ref", ref: "/employees/categories/", width: 4 },
            { name: "location", label: "Location", type: "ref", ref: "/org/locations/", width: 4 },
            { name: "default_shift", label: "Default shift", type: "ref", ref: "/attendance/shifts/", width: 6 },
            { name: "weekend_days", label: "Rest days", type: "json", helper: WEEKDAYS, width: 6 },
            { name: "overtime_after_minutes", label: "Count OT after (min)", type: "number", width: 4 },
            { name: "rounding_minutes", label: "Round OT to (min)", type: "number", width: 4 },
            { name: "max_overtime_hours_month", label: "OT cap per month (h)", type: "number", width: 4 },
            { name: "half_day_minutes", label: "Half-day below (min)", type: "number", width: 4 },
            { name: "priority", label: "Priority (lower wins)", type: "number", width: 4 },
            { name: "overtime_requires_approval", label: "OT needs approval", type: "checkbox", width: 4 },
            { name: "allow_web_clock", label: "Allow web/mobile clock-in", type: "checkbox", width: 4 },
            { name: "require_geofence", label: "Require location (geofence)", type: "checkbox", width: 4 },
            { name: "absent_deduction", label: "Deduct unexcused absence in payroll", type: "checkbox", width: 4 },
            { name: "is_active", label: "Active", type: "checkbox", width: 4 }]}
          defaults={{ weekend_days: "[5, 6]", overtime_after_minutes: 30, rounding_minutes: 15, half_day_minutes: 240, priority: 100,
            overtime_requires_approval: true, allow_web_clock: true, is_active: true }} />}
        {tab === 2 && <ResourcePage embedded title="Pattern" url="/attendance/patterns/" canDelete
          columns={[{ key: "name", label: "Name" }, { key: "sequence", label: "Cycle (shift ids; null = off)", render: (r) => JSON.stringify(r.sequence) }]}
          fields={[{ name: "name", label: "Name", required: true },
            { name: "sequence", label: "Sequence", type: "json", required: true, helper: "Shift ids in order, null for a day off. e.g. [1, 1, 4, 4, null, null]" }]} />}
        {tab === 3 && <ResourcePage embedded title="Device" url="/attendance/devices/" canDelete
          columns={[{ key: "name", label: "Name" }, { key: "ip_address", label: "IP" }, { key: "port", label: "Port" },
            { key: "last_sync_at", label: "Last sync", render: (r) => fmtDateTime(r.last_sync_at as string) }, { key: "last_sync_status", label: "Status" }]}
          rowActions={(r) => <Button size="small" onClick={async () => { const res = await post<{ status: string }>(`/attendance/devices/${r.id}/sync/`); toast.info(res.status); inv("/attendance/devices/"); }}>Sync now</Button>}
          fields={[{ name: "name", label: "Name", required: true, width: 6 }, { name: "serial_number", label: "Serial", width: 6 },
            { name: "ip_address", label: "IP address", required: true, width: 6 }, { name: "port", label: "Port", type: "number", width: 3 },
            { name: "comm_key", label: "Comm key", type: "number", width: 3 }, { name: "location", label: "Location", type: "ref", ref: "/org/locations/", width: 6 },
            { name: "direction", label: "Direction", type: "select", width: 6, options: [{ value: "auto", label: "Auto (from punch type)" }, { value: "in", label: "In only" }, { value: "out", label: "Out only" }] },
            { name: "is_active", label: "Active (synced every 10 minutes)", type: "checkbox" }]} defaults={{ port: 4370, comm_key: 0, direction: "auto", is_active: true }} />}
        {tab === 4 && <ResourcePage embedded title="Enrolment" url="/attendance/enrollments/" canDelete
          columns={[{ key: "employee_name", label: "Employee" }, { key: "device_user_id", label: "Device user ID" }]}
          fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})`, required: true },
            { name: "device_user_id", label: "User ID on terminal", required: true }]} />}
      </Card>
    </>
  );
}
