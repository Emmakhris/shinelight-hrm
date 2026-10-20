import Add from "@mui/icons-material/Add";
import EventRepeat from "@mui/icons-material/EventRepeat";
import { Button, Card } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { post, useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";

export default function Runs() {
  const { can } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const inv = useInvalidate();
  const [newPeriod, setNewPeriod] = useState(false);
  const [newRun, setNewRun] = useState(false);
  const runs = useList("/payroll/runs/");
  const periods = useList<{ id: number; name: string; pay_group_name: string; status: string; start_date: string; end_date: string; pay_date: string }>("/payroll/periods/");
  const groups = useList<{ id: number; name: string }>(newPeriod ? "/payroll/pay-groups/" : null);
  const now = new Date();
  return (
    <>
      <PageHeader title="Payroll runs" subtitle="Draft → Calculated → Submitted → Approved → Released. The preparer cannot approve or release."
        actions={can("payroll.prepare") && <>
          <Button startIcon={<EventRepeat />} onClick={() => setNewPeriod(true)}>New period</Button>
          <Button variant="contained" startIcon={<Add />} onClick={() => setNewRun(true)}>New run</Button>
        </>} />
      <Card>
        <DataTable loading={runs.isLoading} rows={runs.items} onRowClick={(r) => nav(`/payroll/runs/${r.id}`)} columns={[
          { key: "period_name", label: "Period" }, { key: "run_type_label", label: "Type" }, { key: "number", label: "#" },
          { key: "pay_date", label: "Pay date", render: (r) => fmtDate(r.pay_date as string) },
          { key: "employees", label: "Employees", align: "right", render: (r) => (r.totals as Record<string, string>).employees ?? "—" },
          { key: "gross", label: "Gross", align: "right", render: (r) => fmtMoney((r.totals as Record<string, string>).gross) },
          { key: "net", label: "Net", align: "right", render: (r) => fmtMoney((r.totals as Record<string, string>).net) },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} label={r.status_label as string} /> },
        ]} />
      </Card>
      <Section title="Pay periods" dense>
        <DataTable dense rows={periods.items} columns={[{ key: "name", label: "Period" }, { key: "pay_group_name", label: "Pay group" },
          { key: "start_date", label: "Start", render: (r) => fmtDate(r.start_date as string) }, { key: "end_date", label: "End", render: (r) => fmtDate(r.end_date as string) },
          { key: "pay_date", label: "Pay date", render: (r) => fmtDate(r.pay_date as string) }, { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
          { key: "_a", label: "", render: (r) => r.status === "open" && can("payroll.prepare") ? <Button size="small" onClick={async () => {
            const res = await post<{ created: number; total: string }>(`/payroll/periods/${r.id}/retro-arrears/`); toast.ok(`${res.created} arrears adjustment(s) totalling GHS ${res.total}.`);
          }}>Compute retro arrears</Button> : null }]} />
      </Section>
      <FormDialog open={newPeriod} onClose={() => setNewPeriod(false)} title="Create pay period"
        fields={[{ name: "pay_group", label: "Pay group", type: "select", required: true, options: groups.items.map((g) => ({ value: g.id, label: g.name })) },
          { name: "year", label: "Year", type: "number", required: true, width: 4 }, { name: "month", label: "Month (1-12)", type: "number", required: true, width: 4 },
          { name: "pay_day", label: "Pay day", type: "number", width: 4 }]}
        initial={{ year: now.getFullYear(), month: now.getMonth() + 1, pay_day: 25 }}
        onSubmit={async (d) => { await post("/payroll/periods/generate/", d); toast.ok("Period created."); inv("/payroll/"); }} />
      <FormDialog open={newRun} onClose={() => setNewRun(false)} title="New payroll run"
        intro="Supplementary runs pay one-off adjustments only. Final settlement runs pay exiting staff and recover outstanding loans."
        fields={[{ name: "period", label: "Period", type: "select", required: true, options: periods.items.filter((p) => p.status === "open").map((p) => ({ value: p.id, label: `${p.name} (${p.pay_group_name})` })) },
          { name: "run_type", label: "Run type", type: "select", required: true, options: [{ value: "regular", label: "Regular" }, { value: "supplementary", label: "Supplementary" }, { value: "final", label: "Final settlement" }] },
          { name: "employees", label: "Limit to employees (supplementary/final)", type: "multiref", ref: "/employees/", refParams: { include_exited: 1 }, refLabel: (e) => `${e.full_name} (${e.staff_number})` },
          { name: "description", label: "Description" }]}
        initial={{ run_type: "regular" }}
        onSubmit={async (d) => { const r = await post<{ id: number }>("/payroll/runs/", d); inv("/payroll/"); nav(`/payroll/runs/${r.id}`); }} />
    </>
  );
}
