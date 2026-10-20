import Download from "@mui/icons-material/Download";
import Tune from "@mui/icons-material/Tune";
import { Button, Card, MenuItem, TextField } from "@mui/material";
import { useState } from "react";
import { download } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";

export default function LeaveBalances() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [adjusting, setAdjusting] = useState(false);
  const { data, isLoading } = useApi<{ headers: string[]; rows: unknown[][] }>("/leave/requests/report/balances/", { year });
  const types = useList<{ id: number; name: string }>("/leave/types/");
  const emps = useList<{ id: number; full_name: string; staff_number: string }>(adjusting ? "/employees/" : null);
  const toast = useToast();
  const inv = useInvalidate();
  const rows = (data?.rows || []).map((r, i) => Object.fromEntries([["id", i], ...r.map((v, j) => [`c${j}`, v])]));
  return (
    <>
      <PageHeader title="Leave balances" subtitle="Available balance = entitlement + carry-over + adjustments − taken − pending"
        actions={<>
          <TextField select label="Year" value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {[0, 1, 2].map((d) => new Date().getFullYear() - d).map((y) => <MenuItem key={y} value={y}>{y}</MenuItem>)}
          </TextField>
          <Button startIcon={<Download />} onClick={() => download("/leave/requests/report/balances/", { year, format: "xlsx" })}>Export</Button>
          <Button variant="contained" startIcon={<Tune />} onClick={() => setAdjusting(true)}>Adjust balance</Button>
        </>} />
      <Card><DataTable dense loading={isLoading} rows={rows} columns={(data?.headers || []).map((h, j) => ({ key: `c${j}`, label: h, align: j > 2 ? "right" as const : undefined,
        render: j > 2 ? (r: Record<string, unknown>) => Number(r[`c${j}`]) : undefined }))} /></Card>
      <FormDialog open={adjusting} onClose={() => setAdjusting(false)} title="Adjust leave balance" submitLabel="Post adjustment"
        intro="Adjustments are recorded in the employee's leave ledger with your name and reason. Use negative numbers to deduct."
        fields={[
          { name: "employee", label: "Employee", type: "select", required: true, options: emps.items.map((e) => ({ value: e.id, label: `${e.full_name} (${e.staff_number})` })) },
          { name: "leave_type", label: "Leave type", type: "select", required: true, options: types.items.map((t) => ({ value: t.id, label: t.name })), width: 6 },
          { name: "days", label: "Days (+/−)", type: "number", required: true, width: 6 },
          { name: "year", label: "Leave year", type: "number", width: 6 },
          { name: "note", label: "Reason", required: true },
        ]} initial={{ year }}
        onSubmit={async (d) => { await post("/leave/requests/adjust/", d); toast.ok("Balance adjusted."); inv("/leave/"); }} />
    </>
  );
}
