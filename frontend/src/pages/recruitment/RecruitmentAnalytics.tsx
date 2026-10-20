import { Card, CardContent, Grid2 as Grid } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../api/hooks";
import { BarList, ChartTitle } from "../../components/Charts";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading } from "../../components/Feedback";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function RecruitmentAnalytics() {
  const nav = useNavigate();
  const q = useApi<R>("/recruitment/analytics/");
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const d = q.data;
  const days = (v: number | null) => (v == null ? "—" : `${v} days`);
  return (
    <>
      <PageHeader title="Recruitment analytics" subtitle="Time to hire, vacancy ageing, conversion and sources." />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Open vacancies", d.open_vacancies, () => nav("/recruitment/vacancies")], ["Active candidates", d.active_applications],
          ["Hires", d.hires], ["Pending requisitions", d.pending_requisitions, () => nav("/recruitment/requisitions")],
          ["Avg time to hire", days(d.avg_time_to_hire_days)], ["Avg time to fill", days(d.avg_time_to_fill_days)],
          ["Offer acceptance", d.offer_acceptance_percent == null ? "—" : `${d.offer_acceptance_percent}%`],
          ["Cost per hire", d.cost_per_hire == null ? "—" : fmtMoney(d.cost_per_hire)]].map(([label, value, onClick]) => (
          <Grid key={label as string} size={{ xs: 6, md: 3 }}><Kpi label={label as string} value={value as string} onClick={onClick as () => void} /></Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card><CardContent>
            <ChartTitle>Candidate funnel (furthest stage reached)</ChartTitle>
            <BarList data={d.funnel.map((f: R) => ({ label: f.stage, value: f.count }))} valueLabel="Candidates" />
          </CardContent></Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card><CardContent>
            <ChartTitle>Applications by source</ChartTitle>
            <BarList data={d.sources.map((s: R) => ({ label: s.source, value: s.applications }))} valueLabel="Applications" />
          </CardContent></Card>
        </Grid>
        <Grid size={12}>
          <Card><CardContent>
            <ChartTitle>Vacancy ageing (open postings)</ChartTitle>
            <DataTable dense rows={d.vacancy_ageing} onRowClick={(r) => nav(`/recruitment/vacancies/${r.id}`)} emptyTitle="No open vacancies"
              columns={[{ key: "reference", label: "Ref" }, { key: "title", label: "Vacancy" },
                { key: "days_open", label: "Days open", align: "right" }, { key: "applications", label: "Applications", align: "right" },
                { key: "closing_date", label: "Closes", render: (r) => fmtDate(r.closing_date) }]} />
            <DataTable dense rows={d.sources} rowKey={(r) => r.source} columns={[{ key: "source", label: "Source" },
              { key: "applications", label: "Applications", align: "right" }, { key: "hires", label: "Hires", align: "right" },
              { key: "rate", label: "Hire rate", align: "right", render: (r) => (r.applications ? `${Math.round((100 * r.hires) / r.applications)}%` : "—") }]} />
          </CardContent></Card>
        </Grid>
      </Grid>
    </>
  );
}
