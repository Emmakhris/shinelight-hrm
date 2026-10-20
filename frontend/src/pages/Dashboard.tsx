import { Alert, Grid2 as Grid, List, ListItemButton, ListItemText, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useApi } from "../api/hooks";
import { BarList } from "../components/Charts";
import { ErrorAlert, Loading } from "../components/Feedback";
import { Kpi, PageHeader, Section } from "../components/PageHeader";
import { fmtDate, fmtMoney, titleCase } from "../utils";

type D = { label: string; value: number };
interface Dash {
  as_of: string; headcount: number; on_probation: number; new_hires_month: number; new_hires_ytd: number;
  exits_month: number; exits_ytd: number; by_department: D[]; by_employment_type: D[]; by_gender: D[]; by_grade: D[];
  by_location: D[]; establishment: { approved: number; vacant: number; filled: number }; pending_leave_approvals: number;
  on_leave_today: number; attendance_exceptions_yesterday: number; absent_yesterday: number; late_yesterday: number;
  overtime_pending_approval: number; my_pending_tasks: number; overdue_tasks: number; record_completeness?: number;
  expiring: { contracts: Record<string, string>[]; probation: Record<string, string>[]; documents: number; retirements_12m: number };
  payroll?: { current: null | { id: number; period: string; status: string; net: string; employees: number };
    last_paid: null | { id: number; period: string; gross: string; net: string; employer_cost: string; paye: string; ssnit: string } };
}

export default function Dashboard() {
  const { data, isLoading, error } = useApi<Dash>("/reports/dashboard/");
  const nav = useNavigate();
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const d = data;
  return (
    <>
      <PageHeader title="HR dashboard" subtitle={`Operational overview as of ${fmtDate(d.as_of)} · figures reflect your data scope`} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[
          { label: "Headcount", value: d.headcount, hint: `${d.on_probation} on probation`, to: "/employees" },
          { label: "New hires (month / YTD)", value: `${d.new_hires_month} / ${d.new_hires_ytd}` },
          { label: "Exits (month / YTD)", value: `${d.exits_month} / ${d.exits_ytd}` },
          { label: "Vacant approved posts", value: d.establishment.vacant, hint: `${d.establishment.filled} of ${d.establishment.approved} filled`, to: "/org/positions" },
          { label: "Leave awaiting approval", value: d.pending_leave_approvals, hint: `${d.on_leave_today} on leave today`, to: "/leave/requests" },
          { label: "Attendance exceptions (yesterday)", value: d.attendance_exceptions_yesterday, hint: `${d.absent_yesterday} absent · ${d.late_yesterday} late`, to: "/attendance/days" },
          { label: "Overtime awaiting approval", value: d.overtime_pending_approval, to: "/attendance/days" },
          { label: "My pending approvals", value: d.my_pending_tasks, hint: `${d.overdue_tasks} overdue`, to: "/inbox", color: d.overdue_tasks ? "#b91c1c" : undefined },
        ].map((k) => (
          <Grid key={k.label} size={{ xs: 6, md: 3 }}>
            <Kpi label={k.label} value={k.value} hint={k.hint} color={k.color} onClick={k.to ? () => nav(k.to!) : undefined} />
          </Grid>
        ))}
      </Grid>
      {d.payroll && (
        <Section title="Payroll status">
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 4 }}>
              {d.payroll.current ? (
                <Stack spacing={0.5}>
                  <Typography variant="body2" color="text.secondary">Current run</Typography>
                  <Typography fontWeight={650}>{d.payroll.current.period} — {d.payroll.current.status}</Typography>
                  <Typography variant="body2">{d.payroll.current.employees} employees · net {fmtMoney(d.payroll.current.net)}</Typography>
                </Stack>
              ) : <Alert severity="info">No payroll run yet.</Alert>}
            </Grid>
            {d.payroll.last_paid && ([
              ["Last paid gross", d.payroll.last_paid.gross], ["Employer cost", d.payroll.last_paid.employer_cost],
              ["PAYE", d.payroll.last_paid.paye], ["SSNIT (total)", d.payroll.last_paid.ssnit]] as const).map(([l, v]) => (
              <Grid key={l} size={{ xs: 6, md: 2 }}><Kpi label={`${l} (${d.payroll!.last_paid!.period})`} value={fmtMoney(v)} /></Grid>
            ))}
          </Grid>
        </Section>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="Headcount by department"><BarList data={d.by_department} /></Section>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="Headcount by grade"><BarList data={d.by_grade} /></Section>
          <Section title="Employment type"><BarList data={d.by_employment_type.map((x) => ({ ...x, label: titleCase(x.label) }))} /></Section>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Contracts ending (60 days)">
            {d.expiring.contracts.length === 0 ? <Typography variant="body2" color="text.secondary">None</Typography> : (
              <List dense disablePadding>
                {d.expiring.contracts.map((c) => (
                  <ListItemButton key={c.id} onClick={() => nav(`/employees/${c.id}`)}>
                    <ListItemText primary={`${c.first_name} ${c.last_name}`} secondary={`${c.staff_number} · ends ${fmtDate(c.contract_end_date)}`} />
                  </ListItemButton>
                ))}
              </List>
            )}
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Probation reviews due">
            {d.expiring.probation.length === 0 ? <Typography variant="body2" color="text.secondary">None</Typography> : (
              <List dense disablePadding>
                {d.expiring.probation.map((c) => (
                  <ListItemButton key={c.id} onClick={() => nav(`/employees/${c.id}`)}>
                    <ListItemText primary={`${c.first_name} ${c.last_name}`} secondary={`ends ${fmtDate(c.probation_end_date)}`} />
                  </ListItemButton>
                ))}
              </List>
            )}
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Compliance">
            <Stack spacing={1.5}>
              <Typography variant="body2">Documents expiring in 60 days: <b>{d.expiring.documents}</b></Typography>
              <Typography variant="body2">Retirements in next 12 months: <b>{d.expiring.retirements_12m}</b></Typography>
              {d.record_completeness !== undefined && (
                <Typography variant="body2">Employee records complete: <b>{d.record_completeness}%</b></Typography>
              )}
            </Stack>
          </Section>
        </Grid>
      </Grid>
    </>
  );
}
