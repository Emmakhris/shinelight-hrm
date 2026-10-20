import Add from "@mui/icons-material/Add";
import { Button, Card, MenuItem, TextField } from "@mui/material";
import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { post, useInvalidate, useList } from "../../api/hooks";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, titleCase, today } from "../../utils";
import ApplyLeaveDialog from "./ApplyLeaveDialog";

export default function LeaveRequests() {
  const { can } = useAuth();
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [recall, setRecall] = useState<Record<string, unknown> | null>(null);
  const [ret, setRet] = useState<Record<string, unknown> | null>(null);
  const [onBehalf, setOnBehalf] = useState(false);
  const [emp, setEmp] = useState<number | undefined>();
  const types = useList<{ id: number; name: string }>("/leave/types/");
  const emps = useList<{ id: number; full_name: string; staff_number: string }>(onBehalf ? "/employees/" : null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Leave requests" subtitle="All leave in your scope. Approvals are made in the Approvals inbox."
        actions={can("leave.manage") && <Button startIcon={<Add />} variant="contained" onClick={() => setOnBehalf(true)}>Apply on behalf</Button>} />
      <Card>
        <ResourcePage embedded title="Leave" url="/leave/requests/" params={{ status, leave_type: type }}
          filters={<>
            <TextField select label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
              <MenuItem value="">All</MenuItem>
              {["pending", "approved", "rejected", "returned", "cancelled", "recalled"].map((s) => <MenuItem key={s} value={s}>{titleCase(s)}</MenuItem>)}
            </TextField>
            <TextField select label="Type" value={type} onChange={(e) => setType(e.target.value)} sx={{ minWidth: 180 }}>
              <MenuItem value="">All types</MenuItem>
              {types.items.map((t) => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
            </TextField>
          </>}
          columns={[
            { key: "employee_name", label: "Employee" }, { key: "department_name", label: "Department", hideOnMobile: true },
            { key: "leave_type_name", label: "Type" },
            { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) },
            { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date as string) },
            { key: "days", label: "Days", align: "right", render: (r) => Number(r.days) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
            { key: "actual_return_date", label: "Returned", render: (r) => fmtDate(r.actual_return_date as string), hideOnMobile: true },
          ]}
          rowActions={(r) => r.status === "approved" ? (<>
            {(r.start_date as string) <= today() && (r.end_date as string) >= today() && can("leave.approve") &&
              <Button size="small" color="warning" onClick={() => setRecall(r)}>Recall</Button>}
            {(r.end_date as string) < today() && !r.actual_return_date && <Button size="small" onClick={() => setRet(r)}>Record return</Button>}
          </>) : null} />
      </Card>
      <FormDialog open={!!recall} onClose={() => setRecall(null)} title={`Recall ${recall?.employee_name} from leave`} submitLabel="Recall"
        intro="Unused days from the recall date are credited back and the employee is notified."
        fields={[{ name: "recall_date", label: "Recall effective date", type: "date", required: true }, { name: "reason", label: "Reason", type: "textarea", required: true }]}
        initial={{ recall_date: today() }}
        onSubmit={async (d) => { const r = await post<{ detail: string }>(`/leave/requests/${recall!.id}/recall/`, d); toast.ok(r.detail); inv("/leave/"); }} />
      <FormDialog open={!!ret} onClose={() => setRet(null)} title="Record return to work" initial={{ return_date: today() }}
        fields={[{ name: "return_date", label: "Date resumed", type: "date", required: true }, { name: "notes", label: "Notes / follow-up", type: "textarea" }]}
        onSubmit={async (d) => { await post(`/leave/requests/${ret!.id}/confirm_return/`, d); toast.ok("Return recorded."); inv("/leave/"); }} />
      {onBehalf && !emp && (
        <FormDialog open onClose={() => setOnBehalf(false)} title="Apply on behalf of" submitLabel="Continue"
          fields={[{ name: "employee", label: "Employee", type: "select", required: true, options: emps.items.map((e) => ({ value: e.id, label: `${e.full_name} (${e.staff_number})` })) }]}
          onSubmit={async (d) => { setEmp(Number((d as Record<string, unknown>).employee)); }} />
      )}
      <ApplyLeaveDialog open={!!emp} employee={emp} onClose={() => { setEmp(undefined); setOnBehalf(false); }} />
    </>
  );
}
