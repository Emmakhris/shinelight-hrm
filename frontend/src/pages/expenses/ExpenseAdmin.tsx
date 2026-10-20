import Download from "@mui/icons-material/Download";
import { Button, Card, MenuItem, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { download } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney, titleCase } from "../../utils";

export default function ExpenseAdmin() {
  const { can } = useAuth();
  const pay = can("expenses.pay");
  const [tab, setTab] = useState(0);
  const [status, setStatus] = useState("");
  const [advanceFor, setAdvanceFor] = useState<Record<string, any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [settleFor, setSettleFor] = useState<Record<string, any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const outstanding = useApi<{ headers: string[]; rows: unknown[][] }>(tab === 2 ? "/expenses/travel/outstanding-advances/" : null);
  const toast = useToast();
  const inv = useInvalidate();
  const statusFilter = (
    <TextField select label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
      <MenuItem value="">All</MenuItem>{["pending", "approved", "completed", "paid", "retired", "rejected"].map((s) => <MenuItem key={s} value={s}>{titleCase(s)}</MenuItem>)}
    </TextField>
  );
  return (
    <>
      <PageHeader title="Travel & expense administration" subtitle="Approvals happen in the inbox; finance records advances and settlements here (approvers cannot pay their own approvals)."
        actions={<Button startIcon={<Download />} onClick={() => download("/expenses/claims/export/", { format: "xlsx" })}>Export claims</Button>} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Travel requests" /><Tab label="Expense claims" /><Tab label="Outstanding advances" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Travel" url="/expenses/travel/" params={{ status }} filters={statusFilter}
          columns={[{ key: "reference", label: "Ref" }, { key: "employee_name", label: "Employee" }, { key: "destination", label: "Destination" },
            { key: "departure_date", label: "Dates", render: (r) => `${fmtDate(r.departure_date)} – ${fmtDate(r.return_date)}` },
            { key: "total_estimate", label: "Estimate", align: "right", render: (r) => fmtMoney(r.total_estimate, r.currency) },
            { key: "advance_requested", label: "Advance req.", align: "right", render: (r) => fmtMoney(r.advance_requested, r.currency) },
            { key: "advance_paid", label: "Paid", align: "right", render: (r) => Number(r.advance_paid) ? fmtMoney(r.advance_paid, r.currency) : "—" },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]}
          rowActions={(r) => pay && r.status === "approved" && Number(r.advance_requested) > 0 && !Number(r.advance_paid) ?
            <Button size="small" onClick={() => setAdvanceFor(r)}>Pay advance</Button> : null} />}
        {tab === 1 && <ResourcePage embedded title="Claims" url="/expenses/claims/" params={{ status }} filters={statusFilter}
          columns={[{ key: "reference", label: "Ref" }, { key: "employee_name", label: "Employee" }, { key: "title", label: "Title" },
            { key: "travel_reference", label: "Trip" }, { key: "total", label: "Total", align: "right", render: (r) => fmtMoney(r.total) },
            { key: "net_payable", label: "Net", align: "right", render: (r) => fmtMoney(r.net_payable) },
            { key: "payment_method", label: "Via", render: (r) => titleCase(r.payment_method) },
            { key: "warnings", label: "Flags", render: (r) => (r.warnings as string[]).join("; ") },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]}
          rowActions={(r) => pay && r.status === "approved" ? <Button size="small" onClick={() => setSettleFor(r)}>Settle</Button> : null} />}
        {tab === 2 && <>
          <Button startIcon={<Download />} sx={{ m: 1 }} onClick={() => download("/expenses/travel/outstanding-advances/", { format: "xlsx" })}>Export</Button>
          <DataTable dense loading={outstanding.isLoading} rows={(outstanding.data?.rows || []).map((row, i) => Object.fromEntries([["id", i], ...row.map((x, j) => [`c${j}`, x])]))}
            columns={(outstanding.data?.headers || []).map((h, j) => ({ key: `c${j}`, label: h, render: j === 5 ? (r: Record<string, unknown>) => fmtMoney(r[`c${j}`] as string) : undefined }))} />
        </>}
      </Card>
      <FormDialog open={!!advanceFor} onClose={() => setAdvanceFor(null)} title={`Pay advance — ${advanceFor?.reference}`} submitLabel="Record payment"
        fields={[{ name: "amount", label: "Amount", type: "number", required: true, width: 6 }, { name: "reference", label: "Payment reference", required: true, width: 6 },
          { name: "via_payroll", label: "Pay with the next salary instead of a transfer", type: "checkbox" }]}
        initial={{ amount: advanceFor?.advance_requested }}
        onSubmit={async (d) => { await post(`/expenses/travel/${advanceFor!.id}/pay-advance/`, d); toast.ok("Advance recorded."); inv("/expenses/"); }} />
      <FormDialog open={!!settleFor} onClose={() => setSettleFor(null)} title={`Settle claim ${settleFor?.reference}`} submitLabel="Settle"
        intro={settleFor && Number(settleFor.net_payable) < 0 ? `Employee owes ${fmtMoney(-Number(settleFor.net_payable))} unspent advance.` : `Pay ${fmtMoney(settleFor?.net_payable)} to the employee.`}
        fields={[{ name: "method", label: "Method", type: "select", required: true, options: [{ value: "payroll", label: "Next payroll (reimburse / recover)" }, { value: "bank", label: "Bank / MoMo transfer" }, { value: "cash", label: "Petty cash" }] },
          { name: "reference", label: "Payment / receipt reference", hidden: (v) => v.method === "payroll" }]}
        initial={{ method: settleFor?.payment_method }}
        onSubmit={async (d) => { await post(`/expenses/claims/${settleFor!.id}/settle/`, d); toast.ok("Claim settled."); inv("/expenses/"); }} />
    </>
  );
}
