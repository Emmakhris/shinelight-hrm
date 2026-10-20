import AccessTime from "@mui/icons-material/AccessTime";
import BeachAccess from "@mui/icons-material/BeachAccess";
import Description from "@mui/icons-material/Description";
import Inbox from "@mui/icons-material/Inbox";
import ReceiptLong from "@mui/icons-material/ReceiptLong";
import { Alert, Box, Button, Card, CardActionArea, CardContent, Chip, Grid2 as Grid, LinearProgress, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useApi } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { Loading } from "../components/Feedback";
import { Kpi, Section } from "../components/PageHeader";
import { fmtMoney } from "../utils";

interface Summary {
  pending_tasks: number;
  employee?: { name: string; job_title: string; department: string; supervisor: string };
  leave_balances?: { leave_type_name: string; available: string; entitlement: string; opening: string; taken: string; color: string }[];
  today_shift?: string | null;
  last_payslip?: { id: number; period: string; net_pay: string } | null;
  open_requests?: { id: number; title: string; status: string; waiting_on: string[] }[];
  unacknowledged_policies?: number;
  is_manager?: boolean;
}

export default function Home() {
  const { me, can } = useAuth();
  const nav = useNavigate();
  const { data, isLoading } = useApi<Summary>("/me/summary/");
  if (isLoading || !data) return <Loading />;
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const quick = [
    { label: "Apply for leave", icon: <BeachAccess />, to: "/leave/my?apply=1", show: !!me?.employee },
    { label: "Clock in / out", icon: <AccessTime />, to: "/attendance/my", show: !!me?.employee },
    { label: "My payslips", icon: <ReceiptLong />, to: "/me/payslips", show: !!me?.employee },
    { label: "Request a letter", icon: <Description />, to: "/me/documents", show: !!me?.employee },
    { label: "Approvals", icon: <Inbox />, to: "/inbox", show: data.pending_tasks > 0 },
  ].filter((q) => q.show);
  return (
    <>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5">{greet}, {me?.full_name.split(" ")[0]}</Typography>
        {data.employee && (
          <Typography color="text.secondary">{data.employee.job_title} · {data.employee.department}
            {data.employee.supervisor && ` · Reports to ${data.employee.supervisor}`}</Typography>
        )}
      </Box>
      {!me?.employee && <Alert severity="info" sx={{ mb: 2 }}>Your account is not linked to an employee record. Self-service features are hidden.</Alert>}
      {!!data.unacknowledged_policies && (
        <Alert severity="warning" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => nav("/announcements")}>Review</Button>}>
          You have {data.unacknowledged_policies} policy document(s) to read and acknowledge.
        </Alert>
      )}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {quick.map((q) => (
          <Grid key={q.label} size={{ xs: 6, sm: 4, md: 2.4 }}>
            <Card><CardActionArea onClick={() => nav(q.to)}>
              <CardContent sx={{ textAlign: "center" }}>
                <Box sx={{ color: "primary.main", mb: 0.5 }}>{q.icon}</Box>
                <Typography variant="body2" fontWeight={600}>{q.label}</Typography>
              </CardContent>
            </CardActionArea></Card>
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 8 }}>
          {data.leave_balances && (
            <Section title="My leave balances" actions={<Button size="small" onClick={() => nav("/leave/my")}>View all</Button>}>
              <Grid container spacing={2}>
                {data.leave_balances.map((b) => {
                  const total = Number(b.entitlement) + Number(b.opening);
                  const pct = total ? Math.min(100, (Number(b.taken) / total) * 100) : 0;
                  return (
                    <Grid key={b.leave_type_name} size={{ xs: 12, sm: 6 }}>
                      <Stack direction="row" justifyContent="space-between">
                        <Typography variant="body2" fontWeight={600}>{b.leave_type_name}</Typography>
                        <Typography variant="body2"><b>{Number(b.available)}</b> day(s) available</Typography>
                      </Stack>
                      <LinearProgress variant="determinate" value={pct} sx={{ height: 6, borderRadius: 3, my: 0.5 }} />
                      <Typography variant="caption" color="text.secondary">{Number(b.taken)} taken of {total}</Typography>
                    </Grid>
                  );
                })}
              </Grid>
            </Section>
          )}
          <Section title="My open requests" actions={<Button size="small" onClick={() => nav("/me/requests")}>All requests</Button>}>
            {(data.open_requests || []).length === 0 ? <Typography variant="body2" color="text.secondary">No open requests.</Typography> :
              <Stack spacing={1}>
                {data.open_requests!.map((r) => (
                  <Stack key={r.id} direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">{r.title}</Typography>
                    <Chip variant="outlined" label={r.status === "returned" ? "Returned to you" : `Waiting on ${r.waiting_on.join(", ") || "—"}`}
                      color={r.status === "returned" ? "warning" : "default"} />
                  </Stack>
                ))}
              </Stack>}
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Stack spacing={2}>
            {data.pending_tasks > 0 && <Kpi label="Requests awaiting my approval" value={data.pending_tasks} onClick={() => nav("/inbox")} color="#b45309" />}
            {me?.employee && <Kpi label="Today's shift" value={data.today_shift || "Not scheduled / day off"} onClick={() => nav("/attendance/my")} />}
            {data.last_payslip && <Kpi label={`Last payslip (${data.last_payslip.period})`} value={fmtMoney(data.last_payslip.net_pay)} hint="Net pay" onClick={() => nav("/me/payslips")} />}
            {data.is_manager && <Button variant="outlined" onClick={() => nav("/team")}>Go to my team</Button>}
            {can("reports.view") && <Button variant="outlined" onClick={() => nav("/dashboard")}>Open HR dashboard</Button>}
          </Stack>
        </Grid>
      </Grid>
    </>
  );
}
