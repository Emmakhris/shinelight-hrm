import { Card, Stack, TextField } from "@mui/material";
import dayjs from "dayjs";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { PageHeader } from "../../components/PageHeader";

export default function Staffing() {
  const [start, setStart] = useState(dayjs().format("YYYY-MM-DD"));
  const [end, setEnd] = useState(dayjs().add(2, "day").format("YYYY-MM-DD"));
  const { data, isLoading } = useApi<Record<string, unknown>[]>("/attendance/roster/staffing/", { start, end });
  return (
    <>
      <PageHeader title="Ward & department staffing" subtitle="Rostered staff per unit and shift, including emergency and on-call assignments"
        actions={<Stack direction="row" spacing={1}>
          <TextField type="date" label="From" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
          <TextField type="date" label="To" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
        </Stack>} />
      <Card><DataTable dense loading={isLoading} rows={(data || []).map((r, i) => ({ ...r, id: i }))} emptyTitle="No rostered shifts in this range"
        columns={[{ key: "date", label: "Date", render: (r) => dayjs(r.date as string).format("ddd DD/MM") }, { key: "department", label: "Unit" },
          { key: "shift", label: "Shift" }, { key: "count", label: "Staff", align: "right" },
          { key: "staff", label: "Names", render: (r) => (r.staff as string[]).join(", ") }]} /></Card>
    </>
  );
}
