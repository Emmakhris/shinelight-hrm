import InfoOutlined from "@mui/icons-material/InfoOutlined";
import { Grid2 as Grid, Table, TableBody, TableCell, TableHead, TableRow, Tooltip } from "@mui/material";
import { useApi } from "../api/hooks";
import { BarList, Columns, Trend } from "../components/Charts";
import { ErrorAlert, Loading } from "../components/Feedback";
import { Kpi, PageHeader, Section } from "../components/PageHeader";
import { fmtMoney, titleCase } from "../utils";

type D = { label: string; value: number };
interface A {
  turnover_rate: number; voluntary_turnover_rate: number; retention_rate: number | null; absence_rate: number | null;
  sla_compliance: number | null; avg_approval_hours: number | null; self_service_rate: number | null; promotions_12m: number;
  exit_reasons: { exit_reason: string; n: number }[]; trend: Record<string, string | number>[]; age_bands: D[];
  tenure_bands: D[]; retirement_forecast: { year: number; count: number }[];
  kpi_definitions: Record<string, { name: string; formula: string; source: string; frequency: string }>;
  cost_by_department?: { department: string; gross: string; employer_cost: string; headcount: number; period: string }[];
}

const pct = (v: number | null) => (v === null || v === undefined ? "—" : `${v}%`);

export default function Analytics() {
  const { data, isLoading, error } = useApi<A>("/reports/analytics/");
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const def = (k: string) => data.kpi_definitions[k]?.formula;
  const kpis = [
    { k: "turnover_rate", label: "Turnover (12 months)", v: pct(data.turnover_rate), hint: `Voluntary ${pct(data.voluntary_turnover_rate)}` },
    { k: "retention_rate", label: "12-month retention", v: pct(data.retention_rate) },
    { k: "absence_rate", label: "Absence rate (90 days)", v: pct(data.absence_rate) },
    { k: "sla_compliance", label: "Approvals within SLA", v: pct(data.sla_compliance) },
    { k: "avg_approval_hours", label: "Avg approval turnaround", v: data.avg_approval_hours === null ? "—" : `${data.avg_approval_hours} h` },
    { k: "self_service_rate", label: "Self-service adoption", v: pct(data.self_service_rate) },
  ];
  return (
    <>
      <PageHeader title="Workforce analytics" subtitle="Strategic KPIs — hover the info icon for each definition" />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {kpis.map((x) => (
          <Grid key={x.k} size={{ xs: 6, md: 2 }}>
            <Kpi label={x.label} value={<>{x.v} <Tooltip title={def(x.k) || ""}><InfoOutlined sx={{ fontSize: 16, color: "text.secondary" }} /></Tooltip></>} hint={x.hint} />
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 8 }}>
          <Section title="Hires and exits per month (last 12 months)">
            <Trend data={data.trend} series={[{ key: "hires", label: "Hires" }, { key: "exits", label: "Exits" }]} />
          </Section>
          <Section title="Headcount trend">
            <Trend data={data.trend} series={[{ key: "headcount", label: "Headcount" }]} height={200} />
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Exit reasons (12 months)">
            <BarList data={data.exit_reasons.map((r) => ({ label: titleCase(r.exit_reason) || "Unspecified", value: r.n }))} valueLabel="Exits" />
          </Section>
          <Section title="Retirement forecast">
            <Columns data={data.retirement_forecast.map((r) => ({ label: String(r.year), value: r.count }))} valueLabel="Retirements" height={180} />
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="Age profile (aggregated)"><Columns data={data.age_bands} /></Section>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="Length of service (years)"><Columns data={data.tenure_bands} /></Section>
        </Grid>
        {data.cost_by_department && data.cost_by_department.length > 0 && (
          <Grid size={12}>
            <Section title={`Workforce cost by department — ${data.cost_by_department[0].period}`} dense>
              <Table size="small">
                <TableHead><TableRow><TableCell>Department</TableCell><TableCell align="right">Headcount</TableCell>
                  <TableCell align="right">Gross pay</TableCell><TableCell align="right">Employer cost</TableCell></TableRow></TableHead>
                <TableBody>
                  {data.cost_by_department.map((r) => (
                    <TableRow key={r.department}><TableCell>{r.department}</TableCell><TableCell align="right">{r.headcount}</TableCell>
                      <TableCell align="right">{fmtMoney(r.gross)}</TableCell><TableCell align="right">{fmtMoney(r.employer_cost)}</TableCell></TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </Grid>
        )}
        <Grid size={12}>
          <Section title="KPI definitions" dense>
            <Table size="small">
              <TableHead><TableRow><TableCell>KPI</TableCell><TableCell>Formula</TableCell><TableCell>Source</TableCell><TableCell>Frequency</TableCell></TableRow></TableHead>
              <TableBody>
                {Object.entries(data.kpi_definitions).map(([k, v]) => (
                  <TableRow key={k}><TableCell>{v.name}</TableCell><TableCell>{v.formula}</TableCell><TableCell>{v.source}</TableCell><TableCell>{v.frequency}</TableCell></TableRow>
                ))}
              </TableBody>
            </Table>
          </Section>
        </Grid>
      </Grid>
    </>
  );
}
