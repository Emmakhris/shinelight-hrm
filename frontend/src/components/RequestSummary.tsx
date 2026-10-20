import { Alert, Box, Grid2 as Grid, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { fmtDate, fmtDateTime, fmtMoney, titleCase } from "../utils";
import { Field } from "./PageHeader";

type Any = Record<string, unknown>;

/** Renders the key facts of a workflow request so an approver can decide from the inbox. */
export function RequestSummary({ type, s }: { type: string; s: Any }) {
  if (!s) return null;
  if (type === "leave_request") {
    return (
      <Box>
        <Grid container spacing={2}>
          <Grid size={6}><Field label="Leave type" value={s.leave_type as string} /></Grid>
          <Grid size={6}><Field label="Days" value={String(s.days)} /></Grid>
          <Grid size={6}><Field label="From" value={fmtDate(s.start_date as string)} /></Grid>
          <Grid size={6}><Field label="To" value={fmtDate(s.end_date as string)} /></Grid>
          <Grid size={6}><Field label="Balance available" value={String(s.balance_available)} /></Grid>
          <Grid size={6}><Field label="Relief officer" value={s.relief_officer as string} /></Grid>
          <Grid size={12}><Field label="Reason" value={s.reason as string} /></Grid>
        </Grid>
        {(s.warnings as string[] | undefined)?.map((w) => <Alert key={w} severity="warning" sx={{ mt: 1 }}>{w}</Alert>)}
      </Box>
    );
  }
  if (type === "employee_change") {
    return (
      <Table size="small">
        <TableHead><TableRow><TableCell>Field</TableCell><TableCell>Current</TableCell><TableCell>Requested</TableCell></TableRow></TableHead>
        <TableBody>
          {(s.changes as Any[]).map((c) => (
            <TableRow key={c.field as string}><TableCell>{titleCase(c.field as string)}</TableCell><TableCell>{String(c.from || "—")}</TableCell>
              <TableCell><b>{String(c.to)}</b></TableCell></TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }
  if (type === "payroll_run") {
    const t = (s.totals || {}) as Any;
    return (
      <Grid container spacing={2}>
        <Grid size={6}><Field label="Period" value={s.period as string} /></Grid>
        <Grid size={6}><Field label="Employees" value={String(t.employees)} /></Grid>
        <Grid size={4}><Field label="Gross" value={fmtMoney(t.gross as string)} /></Grid>
        <Grid size={4}><Field label="Net" value={fmtMoney(t.net as string)} /></Grid>
        <Grid size={4}><Field label="Employer cost" value={fmtMoney(t.employer_cost as string)} /></Grid>
        <Grid size={4}><Field label="PAYE" value={fmtMoney(t.paye as string)} /></Grid>
        <Grid size={4}><Field label="Warnings" value={String(t.warnings)} /></Grid>
        <Grid size={4}><Field label="On hold" value={String(t.on_hold)} /></Grid>
        <Grid size={12}><Typography variant="body2">Open the run to review payslips and the variance report before approving.</Typography></Grid>
      </Grid>
    );
  }
  if (type === "loan_request") {
    return (
      <Grid container spacing={2}>
        <Grid size={6}><Field label="Type" value={s.loan_type as string} /></Grid>
        <Grid size={6}><Field label="Amount" value={fmtMoney(s.principal as string)} /></Grid>
        <Grid size={6}><Field label="Instalments" value={`${s.installments} x ${fmtMoney(s.installment_amount as string)}`} /></Grid>
        <Grid size={6}><Field label="Basic salary" value={fmtMoney(s.basic_salary as string)} /></Grid>
        <Grid size={12}><Field label="Purpose" value={s.purpose as string} /></Grid>
      </Grid>
    );
  }
  if (type === "attendance_correction") {
    return (
      <Grid container spacing={2}>
        <Grid size={4}><Field label="Date" value={fmtDate(s.date as string)} /></Grid>
        <Grid size={4}><Field label="Clock in" value={fmtDateTime(s.clock_in as string)} /></Grid>
        <Grid size={4}><Field label="Clock out" value={fmtDateTime(s.clock_out as string)} /></Grid>
        <Grid size={12}><Field label="Reason" value={s.reason as string} /></Grid>
      </Grid>
    );
  }
  return (
    <Grid container spacing={2}>
      {Object.entries(s).map(([k, v]) => (
        <Grid key={k} size={6}><Field label={titleCase(k)} value={typeof v === "object" ? JSON.stringify(v) : String(v ?? "")} /></Grid>
      ))}
    </Grid>
  );
}
