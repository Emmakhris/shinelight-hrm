import Download from "@mui/icons-material/Download";
import {
  Alert, Button, Card, Chip, Grid2 as Grid, MenuItem, Stack, Tab, Tabs, TextField, Tooltip, Typography,
} from "@mui/material";
import { useState } from "react";
import { download } from "../api/client";
import { useApi } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { BarList, Columns, Trend } from "../components/Charts";
import { DataTable } from "../components/DataTable";
import { ErrorAlert, Loading, useToast } from "../components/Feedback";
import { Kpi, PageHeader, Section } from "../components/PageHeader";
import { fmtDate } from "../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const BAND_COLOR: Record<string, "error" | "warning" | "default"> = { high: "error", medium: "warning", low: "default" };

function Turnover() {
  const { data, isLoading, error } = useApi<R>("/reports/forecast/turnover/");
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const withBands = data.departments.some((d: R) => "risk_high" in d);
  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Current headcount" value={data.headcount} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Expected leavers (12 months)" value={data.expected_leavers} hint={`Likely range ${data.range[0]}–${data.range[1]}`} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Retirements due (12 months)" value={data.retirements_12m} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Organization turnover (12 months)" value={`${data.org_turnover_percent}%`} /></Grid>
      </Grid>
      <Section title="Projected headcount, assuming no replacement hiring">
        <Trend data={data.monthly} series={[{ key: "headcount", label: "Projected headcount" }]} height={220} />
      </Section>
      <Section title="By department" dense>
        <DataTable dense rowKey={(r) => r.department as string} rows={data.departments} columns={[
          { key: "department", label: "Department" },
          { key: "headcount", label: "Headcount", align: "right" },
          { key: "exits_12m", label: "Exits (12 months)", align: "right" },
          { key: "turnover_percent", label: "Actual turnover", align: "right", render: (r) => `${r.turnover_percent}%` },
          { key: "forecast_rate_percent", label: "Forecast rate", align: "right", render: (r) => `${r.forecast_rate_percent}%` },
          { key: "expected_leavers", label: "Expected leavers", align: "right" },
          { key: "retirements_12m", label: "Retirements", align: "right" },
          ...(withBands ? [{ key: "risk_high", label: "High-risk indicators", align: "right" as const },
            { key: "risk_medium", label: "Medium", align: "right" as const }] : []),
        ]} />
      </Section>
      <Alert severity="info">{data.method}</Alert>
    </>
  );
}

function Retirement() {
  const [years, setYears] = useState(5);
  const { data, isLoading, error } = useApi<R>(`/reports/forecast/retirement/?years=${years}`);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  return (
    <>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <TextField select size="small" label="Horizon" value={years} onChange={(e) => setYears(Number(e.target.value))}>
          {[3, 5, 10].map((y) => <MenuItem key={y} value={y}>{y} years</MenuItem>)}
        </TextField>
        <Typography variant="body2" color="text.secondary">
          Retirement age {data.retirement_age}.{data.estimated_dates > 0 && ` ${data.estimated_dates} date(s) estimated from date of birth because no retirement date is recorded.`}
        </Typography>
      </Stack>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}><Section title="Retirements per year"><Columns data={data.by_year} valueLabel="Retirements" /></Section></Grid>
        <Grid size={{ xs: 12, md: 6 }}><Section title="Most affected job titles"><BarList data={data.by_job_title} valueLabel="Retirements" /></Section></Grid>
      </Grid>
      <Section title="Critical positions losing their incumbent" dense>
        <DataTable dense rowKey={(r) => r.position as string} rows={data.critical_positions} emptyTitle="No critical positions affected" columns={[
          { key: "position", label: "Position" },
          { key: "incumbent", label: "Incumbent", render: (r) => r.incumbent ?? "—" },
          { key: "retirement_date", label: "Retires", render: (r) => fmtDate(r.retirement_date) },
          { key: "successors", label: "Successors", align: "right" },
          { key: "ready_now", label: "Ready now", align: "right" },
          { key: "covered", label: "Cover", render: (r) => <Chip size="small" color={r.covered ? "success" : "error"} label={r.covered ? "Ready successor" : "Gap"} /> },
        ]} />
      </Section>
      <Section title="By department" dense>
        <DataTable dense rowKey={(r) => r.department as string} rows={data.by_department} emptyTitle="No retirements in the horizon" columns={[
          { key: "department", label: "Department" },
          ...data.years.map((y: number) => ({ key: String(y), label: String(y), align: "right" as const })),
          { key: "total", label: "Total", align: "right" },
        ]} />
      </Section>
    </>
  );
}

function Risk() {
  const { can } = useAuth();
  const toast = useToast();
  const [band, setBand] = useState("");
  const { data, isLoading, error } = useApi<R>(`/reports/attrition-risk/${band ? `?band=${band}` : ""}`);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const counts = (data.rows as R[]).reduce((a: R, r) => ({ ...a, [r.band]: (a[r.band] || 0) + 1 }), {});
  return (
    <>
      <Alert severity="warning" sx={{ mb: 2 }}>
        These are indicators to prompt a supportive conversation, not predictions or labels. Never use them for decisions about
        pay, promotion, discipline or redundancy. They are hidden from the employee concerned and every view is recorded in the audit log.
      </Alert>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }} sx={{ mb: 2 }}>
        <TextField select size="small" label="Band" value={band} onChange={(e) => setBand(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem><MenuItem value="high">High</MenuItem><MenuItem value="medium">Medium</MenuItem><MenuItem value="low">Low</MenuItem>
        </TextField>
        {!band && <Typography variant="body2" color="text.secondary">{counts.high || 0} high, {counts.medium || 0} medium, {counts.low || 0} low</Typography>}
        {can("reports.export") && <Button size="small" startIcon={<Download />} sx={{ ml: { sm: "auto" } }}
          onClick={() => download("/reports/attrition-risk/", { format: "xlsx", band: band || undefined }, "attrition-risk.xlsx").catch(toast.error)}>Export</Button>}
      </Stack>
      <Card>
        <DataTable dense rowKey={(r) => r.employee as number} rows={data.rows} emptyTitle="No staff in this band" columns={[
          { key: "name", label: "Employee", render: (r) => <><Typography variant="body2" fontWeight={600} component="span">{r.name}</Typography><Typography variant="caption" color="text.secondary" component="span" display="block">{r.staff_number} · {r.job_title}</Typography></> },
          { key: "department", label: "Department" },
          { key: "score", label: "Score", align: "right" },
          { key: "band", label: "Band", render: (r) => <Chip size="small" color={BAND_COLOR[r.band]} label={r.band} /> },
          { key: "factors", label: "Why", render: (r) => <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {(r.factors as R[]).map((f) => <Tooltip key={f.code} title={`${f.detail} (+${f.weight})`}><Chip size="small" variant="outlined" label={f.label} /></Tooltip>)}
          </Stack> },
        ]} />
      </Card>
      <Section title="How the score is built" dense>
        <DataTable dense rowKey={(r) => r.code as string} rows={Object.entries(data.weights).map(([code, w]) => ({ code, weight: w, label: data.labels[code] }))} columns={[
          { key: "label", label: "Indicator" }, { key: "weight", label: "Points", align: "right" }]} />
        <Typography variant="caption" color="text.secondary">High from {data.thresholds.high} points, medium from {data.thresholds.medium}. A medium manager flag counts half. Weights can be tuned per organization.</Typography>
      </Section>
    </>
  );
}

export default function Forecasts() {
  const { can } = useAuth();
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Workforce forecasts" subtitle="Expected turnover, retirements and attrition-risk indicators within your data scope." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Turnover" /><Tab label="Retirement" />{can("analytics.predictive") && <Tab label="Attrition-risk indicators" />}
      </Tabs>
      {tab === 0 && <Turnover />}
      {tab === 1 && <Retirement />}
      {tab === 2 && can("analytics.predictive") && <Risk />}
    </>
  );
}
