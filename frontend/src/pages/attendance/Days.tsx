import Check from "@mui/icons-material/Check";
import Download from "@mui/icons-material/Download";
import Refresh from "@mui/icons-material/Refresh";
import { Button, Card, FormControlLabel, MenuItem, Stack, Switch, TextField } from "@mui/material";
import dayjs from "dayjs";
import { useState } from "react";
import { download } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { fmtTime, titleCase } from "../../utils";

export default function Days() {
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const [start, setStart] = useState(dayjs().subtract(7, "day").format("YYYY-MM-DD"));
  const [end, setEnd] = useState(dayjs().subtract(1, "day").format("YYYY-MM-DD"));
  const [dept, setDept] = useState("");
  const [exceptions, setExceptions] = useState(true);
  const [ot, setOt] = useState(false);
  const [selected, setSelected] = useState<(string | number)[]>([]);
  const [page, setPage] = useState(1);
  const params = { start, end, employee__department: dept, is_exception: exceptions ? "true" : undefined,
    overtime_status: ot ? "pending" : undefined, page, page_size: 50 };
  const q = useApi<{ count: number; results: Record<string, unknown>[] }>("/attendance/days/", params);
  const depts = useList<{ id: number; name: string }>("/org/departments/");
  const approve = async (yes: boolean) => {
    const r = await post<{ updated: number }>("/attendance/days/approve-overtime/", { ids: selected, approve: yes });
    toast.ok(`${r.updated} overtime record(s) ${yes ? "approved" : "rejected"}.`); setSelected([]); inv("/attendance/");
  };
  return (
    <>
      <PageHeader title="Timesheets & exceptions" subtitle="Late arrivals, absences, missing clock-outs and overtime awaiting approval"
        actions={<>
          {can("attendance.manage") && <Button startIcon={<Refresh />} onClick={async () => { const r = await post<{ processed: number }>("/attendance/days/process/", { start, end }); toast.ok(`Reprocessed ${r.processed} day records.`); inv("/attendance/"); }}>Reprocess</Button>}
          <Button startIcon={<Download />} onClick={() => download("/attendance/days/export/", { ...params, page: undefined, page_size: undefined })}>Export timesheet</Button>
        </>} />
      <Card>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ p: 1.5 }} alignItems={{ md: "center" }}>
          <TextField type="date" label="From" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
          <TextField type="date" label="To" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
          <TextField select label="Department" value={dept} onChange={(e) => setDept(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">All</MenuItem>{depts.items.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
          </TextField>
          <FormControlLabel control={<Switch checked={exceptions} onChange={(e) => setExceptions(e.target.checked)} />} label="Exceptions only" />
          <FormControlLabel control={<Switch checked={ot} onChange={(e) => setOt(e.target.checked)} />} label="Overtime pending" />
          {selected.length > 0 && <>
            <Button variant="contained" color="success" startIcon={<Check />} onClick={() => approve(true)}>Approve OT ({selected.length})</Button>
            <Button color="error" onClick={() => approve(false)}>Reject OT</Button>
          </>}
        </Stack>
        <DataTable dense loading={q.isLoading} rows={q.data?.results || []} selectable={ot} selected={selected} onSelect={setSelected}
          count={q.data?.count} page={page} pageSize={50} onPageChange={setPage}
          columns={[
            { key: "employee_name", label: "Employee" }, { key: "date", label: "Date", render: (r) => dayjs(r.date as string).format("ddd DD/MM") },
            { key: "shift_name", label: "Shift" }, { key: "first_in", label: "In", render: (r) => fmtTime(r.first_in as string) },
            { key: "last_out", label: "Out", render: (r) => fmtTime(r.last_out as string) },
            { key: "worked_minutes", label: "Worked (h)", align: "right", render: (r) => ((r.worked_minutes as number) / 60).toFixed(1) },
            { key: "late_minutes", label: "Late", align: "right" }, { key: "early_leave_minutes", label: "Early", align: "right" },
            { key: "overtime_minutes", label: "OT (h)", align: "right", render: (r) => (r.overtime_minutes ? ((r.overtime_minutes as number) / 60).toFixed(1) : "") },
            { key: "overtime_category", label: "OT type", render: (r) => titleCase(r.overtime_category as string) },
            { key: "overtime_status", label: "OT status", render: (r) => r.overtime_status !== "none" ? <StatusChip value={r.overtime_status as string} /> : "" },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
          ]} />
      </Card>
    </>
  );
}
