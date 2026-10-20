import { Card, Grid2 as Grid } from "@mui/material";
import { useApi } from "../../api/hooks";
import { BarList } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading } from "../../components/Feedback";
import { Kpi, PageHeader, Section } from "../../components/PageHeader";

type M = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const v = (x: unknown, suffix = "") => (x === null || x === undefined ? "—" : `${x}${suffix}`);

export default function Metrics() {
  const { data, isLoading, error } = useApi<M>("/helpdesk/tickets/metrics/");
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  return (
    <>
      <PageHeader title="HR service KPIs" subtitle={`Last ${data.period_days} days. Response and resolution times exclude time waiting on employees.`} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Requests received", v(data.created)], ["Open backlog", v(data.backlog)], ["Overdue", v(data.overdue)],
          ["Avg first response", v(data.avg_first_response_hours, " h")], ["Avg resolution", v(data.avg_resolution_hours, " h")],
          ["Resolved within SLA", v(data.sla_compliance_percent, "%")], ["Satisfaction (CSAT)", data.csat_average ? `${data.csat_average} / 5 (${data.csat_responses})` : "—"],
          ["Self-service share", v(data.self_service_percent, "%")]].map(([l, x]) => (
          <Grid key={l} size={{ xs: 6, md: 3 }}><Kpi label={l} value={x} /></Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}><Section title="Requests by category"><BarList data={data.by_category} valueLabel="Requests" /></Section></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Section title="Requests by channel"><BarList data={data.by_channel} valueLabel="Requests" /></Section></Grid>
        <Grid size={12}>
          <Card>
            <DataTable dense rows={data.agents.map((a: M, i: number) => ({ ...a, id: i }))} columns={[
              { key: "agent", label: "HR officer" }, { key: "total", label: "Received", align: "right" }, { key: "open", label: "Open", align: "right" },
              { key: "resolved", label: "Resolved", align: "right" },
              { key: "avg_resolution_hours", label: "Avg resolution (h)", align: "right", render: (r) => v(r.avg_resolution_hours) },
              { key: "sla_percent", label: "Within SLA", align: "right", render: (r) => v(r.sla_percent, "%") }]} />
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
