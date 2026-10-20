import { Card, Grid2 as Grid, LinearProgress, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading } from "../../components/Feedback";
import { Kpi, PageHeader, Section } from "../../components/PageHeader";
import { titleCase } from "../../utils";

interface DQ { active_employees: number; complete_records: number; completeness_percent: number; missing_fields: Record<string, number>;
  duplicate_ghana_cards: { ghana_card_no: string; n: number }[]; issues: { employee: number; name: string; issue: string }[] }

export default function DataQuality() {
  const { data, isLoading, error } = useApi<DQ>("/employees/data-quality/");
  const nav = useNavigate();
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  return (
    <>
      <PageHeader title="Data quality" subtitle="Missing fields, duplicates and inconsistent records among active employees" />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, md: 4 }}><Kpi label="Records complete" value={`${data.completeness_percent}%`} hint={`${data.complete_records} of ${data.active_employees}`} /></Grid>
        <Grid size={{ xs: 6, md: 4 }}><Kpi label="Issues found" value={data.issues.length} /></Grid>
        <Grid size={{ xs: 6, md: 4 }}><Kpi label="Duplicate Ghana Cards" value={data.duplicate_ghana_cards.length} color={data.duplicate_ghana_cards.length ? "#b91c1c" : undefined} /></Grid>
      </Grid>
      <Section title="Missing mandatory fields">
        <Grid container spacing={2}>
          {Object.entries(data.missing_fields).map(([f, n]) => (
            <Grid key={f} size={{ xs: 12, sm: 6, md: 4 }}>
              <Typography variant="body2">{titleCase(f)}: <b>{n}</b> missing</Typography>
              <LinearProgress variant="determinate" color={n ? "warning" : "success"} value={data.active_employees ? 100 - (n / data.active_employees) * 100 : 100} sx={{ height: 6, borderRadius: 3 }} />
            </Grid>
          ))}
        </Grid>
      </Section>
      <Card>
        <DataTable dense rows={data.issues.map((x, i) => ({ ...x, id: i }))} onRowClick={(r) => nav(`/employees/${r.employee}`)} emptyTitle="No inconsistencies found"
          columns={[{ key: "name", label: "Employee" }, { key: "issue", label: "Issue" }]} />
      </Card>
    </>
  );
}
