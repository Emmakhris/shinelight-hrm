import { Card, Chip, Grid2 as Grid } from "@mui/material";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { fmtTime } from "../../utils";

const STATES: Record<string, { label: string; color: "success" | "warning" | "error" | "info" | "default" }> = {
  in: { label: "In", color: "success" }, late: { label: "Late", color: "warning" }, not_in: { label: "Not in yet", color: "error" },
  on_leave: { label: "On leave", color: "info" }, off: { label: "Day off", color: "default" },
};

export default function TeamToday() {
  const { data, isLoading } = useApi<Record<string, unknown>[]>("/attendance/team-today/", undefined, { refetchInterval: 120000 });
  const rows: Record<string, unknown>[] = (data || []).map((r) => ({ ...r, id: r.employee }));
  const n = (s: string) => rows.filter((r) => r.state === s).length;
  return (
    <>
      <PageHeader title="Team attendance today" subtitle="Refreshes every 2 minutes" />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {Object.entries(STATES).map(([k, v]) => <Grid key={k} size={{ xs: 6, md: 2.4 }}><Kpi label={v.label} value={n(k)} /></Grid>)}
      </Grid>
      <Card>
        <DataTable loading={isLoading} rows={rows} columns={[
          { key: "name", label: "Employee" }, { key: "department", label: "Department" }, { key: "shift", label: "Shift" },
          { key: "first_in", label: "First in", render: (r) => fmtTime(r.first_in as string) },
          { key: "state", label: "Status", render: (r) => <Chip variant="outlined" color={STATES[r.state as string]?.color} label={STATES[r.state as string]?.label} /> },
        ]} />
      </Card>
    </>
  );
}
