import PictureAsPdf from "@mui/icons-material/PictureAsPdf";
import { Alert, Button, Card, CardActions, CardContent, Chip, Grid2 as Grid, Table, TableBody, TableCell, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { openBlob } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function TotalRewards({ employee }: { employee?: number }) {
  const year = new Date().getFullYear();
  const { data } = useApi<R>("/compensation/total-rewards/", { employee, year });
  if (!data) return null;
  return (
    <Section title={`Total rewards ${year}`} actions={<Button size="small" startIcon={<PictureAsPdf />}
      onClick={() => openBlob("/compensation/total-rewards/", { employee, year, format: "pdf" })}>Statement PDF</Button>}>
      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Cash pay to date" value={fmtMoney(data.cash_total)} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Employer contributions" value={fmtMoney(data.employer_total)} hint="SSNIT, provident fund" /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Benefits value" value={fmtMoney(data.benefits_total)} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi label="Total value" value={fmtMoney(data.total)} hint={data.projected_annual_total ? `Projected year: ${fmtMoney(data.projected_annual_total)}` : undefined} /></Grid>
      </Grid>
      <Table size="small"><TableBody>
        {Object.entries(data.cash).map(([k, v]) => <TableRow key={k}><TableCell>{k}</TableCell><TableCell align="right">{fmtMoney(v as string)}</TableCell></TableRow>)}
      </TableBody></Table>
    </Section>
  );
}

export default function MyBenefits() {
  const plans = useList<R>("/benefits/plans/");
  const mine = useList<R>("/benefits/enrollments/", { mine: 1 });
  const [enrolling, setEnrolling] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="My benefits & rewards" />
      <TotalRewards />
      <Section title="My enrolments" dense>
        <Table size="small"><TableBody>
          {mine.items.length === 0 && <TableRow><TableCell>No enrolments yet.</TableCell></TableRow>}
          {mine.items.map((e) => (
            <TableRow key={e.id}><TableCell>{e.plan_name}</TableCell><TableCell>From {fmtDate(e.start_date)}</TableCell>
              <TableCell>{(e.dependants || []).length} dependant(s)</TableCell><TableCell>Your cost {fmtMoney(e.employee_cost)}/month</TableCell>
              <TableCell>{e.member_number && `Member ${e.member_number}`}</TableCell><TableCell><StatusChip value={e.status} /></TableCell></TableRow>
          ))}
        </TableBody></Table>
      </Section>
      <Typography variant="h6" sx={{ mb: 1 }}>Available plans</Typography>
      <Grid container spacing={2}>
        {plans.items.filter((p) => p.is_active).map((p) => (
          <Grid key={p.id} size={{ xs: 12, md: 4 }}>
            <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
              <CardContent sx={{ flex: 1 }}>
                <Typography fontWeight={650}>{p.name}</Typography>
                <Typography variant="caption" color="text.secondary">{p.provider}</Typography>
                <Typography variant="body2" sx={{ my: 1 }}>{p.description}</Typography>
                <Typography variant="body2">Employer pays {fmtMoney(p.employer_monthly_cost)}/month · You pay {fmtMoney(p.employee_monthly_cost)}/month
                  {Number(p.cost_per_dependant) > 0 && ` + ${fmtMoney(p.cost_per_dependant)} per dependant (max ${p.max_dependants})`}</Typography>
                {p.eligible.length > 0 && <Alert severity="info" sx={{ mt: 1 }}>{p.eligible.join(" ")}</Alert>}
              </CardContent>
              <CardActions>
                {p.my_enrollment ? <Chip label={p.my_enrollment.status === "active" ? "Enrolled" : "Pending approval"} color="success" variant="outlined" />
                  : <Button disabled={p.eligible.length > 0} onClick={() => setEnrolling(p)}>Enrol</Button>}
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>
      <FormDialog open={!!enrolling} onClose={() => setEnrolling(null)} title={`Enrol in ${enrolling?.name}`} submitLabel="Submit enrolment"
        fields={[{ name: "start_date", label: "Start date", type: "date", required: true },
          { name: "dependants", label: `Dependants (up to ${enrolling?.max_dependants ?? 0}) — JSON list`, type: "json",
            hidden: () => !enrolling?.max_dependants, helper: '[{"name": "Kwesi Mensah", "relationship": "child", "date_of_birth": "2018-05-01"}]' }]}
        initial={{ start_date: new Date().toISOString().slice(0, 10), dependants: "[]" }}
        onSubmit={async (d) => { await post("/benefits/enrollments/", { ...(d as R), plan: enrolling!.id }); toast.ok("Enrolment submitted."); inv("/benefits/"); }} />
    </>
  );
}
