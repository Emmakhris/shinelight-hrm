import PictureAsPdf from "@mui/icons-material/PictureAsPdf";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid, Table, TableBody, TableCell,
  TableRow, Typography } from "@mui/material";
import { openBlob } from "../api/client";
import { useApi } from "../api/hooks";
import { fmtMoney } from "../utils";
import { Loading } from "./Feedback";
import { Field } from "./PageHeader";

interface Line { id: number; code: string; name: string; line_type: string; amount: string; quantity: string | null; show_on_payslip: boolean }
interface Slip {
  id: number; employee_name: string; staff_number: string; department: string; job_title: string; grade: string; period_name: string;
  pay_date: string; days_payable: string; days_in_period: string; gross_pay: string; total_deductions: string; net_pay: string;
  taxable_income: string; paye: string; ssnit_employer: string; tier1: string; tier2: string; employer_cost: string;
  messages: string[]; lines: Line[]; ytd: Record<string, string>; bank_name: string; account_last4: string; status: string;
}

function Lines({ title, lines, total, totalLabel }: { title: string; lines: Line[]; total: string; totalLabel: string }) {
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>{title}</Typography>
      <Table size="small">
        <TableBody>
          {lines.map((l) => (
            <TableRow key={l.id}><TableCell>{l.name}{l.quantity && l.code !== "BASIC" ? ` (${Number(l.quantity)})` : ""}</TableCell>
              <TableCell align="right">{fmtMoney(l.amount, "")}</TableCell></TableRow>
          ))}
          <TableRow><TableCell sx={{ fontWeight: 700 }}>{totalLabel}</TableCell><TableCell align="right" sx={{ fontWeight: 700 }}>{fmtMoney(total, "")}</TableCell></TableRow>
        </TableBody>
      </Table>
    </Box>
  );
}

export function PayslipDialog({ id, onClose, showDiagnostics }: { id: number | null; onClose: () => void; showDiagnostics?: boolean }) {
  const { data } = useApi<Slip>(id ? `/payroll/payslips/${id}/` : null);
  const visible = (data?.lines || []).filter((l) => l.show_on_payslip);
  return (
    <Dialog open={!!id} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Payslip — {data?.period_name}</DialogTitle>
      <DialogContent dividers>
        {!data ? <Loading /> : (
          <>
            {showDiagnostics && data.messages.length > 0 && (
              <Alert severity={data.status === "error" ? "error" : "warning"} sx={{ mb: 2 }}>{data.messages.join(" • ")}</Alert>
            )}
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid size={{ xs: 6, md: 3 }}><Field label="Name" value={data.employee_name} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Field label="Staff no" value={data.staff_number} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Field label="Department" value={data.department} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Field label="Days paid" value={`${Number(data.days_payable)} / ${Number(data.days_in_period)}`} /></Grid>
            </Grid>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 6 }}><Lines title="Earnings" lines={visible.filter((l) => l.line_type === "earning")} total={data.gross_pay} totalLabel="Gross pay" /></Grid>
              <Grid size={{ xs: 12, md: 6 }}><Lines title="Deductions" lines={visible.filter((l) => l.line_type === "deduction")} total={data.total_deductions} totalLabel="Total deductions" /></Grid>
            </Grid>
            <Box sx={{ mt: 2, p: 2, bgcolor: "#f1f5f9", borderRadius: 2 }}>
              <Typography variant="h6">Net pay: {fmtMoney(data.net_pay)}</Typography>
              <Typography variant="body2" color="text.secondary">Paid to {data.bank_name} ****{data.account_last4} · Chargeable income {fmtMoney(data.taxable_income)}</Typography>
            </Box>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid size={{ xs: 6, md: 3 }}><Field label="Employer SSNIT (13%)" value={fmtMoney(data.ssnit_employer)} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Field label="YTD gross" value={fmtMoney(data.ytd?.gross)} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Field label="YTD tax" value={fmtMoney(data.ytd?.paye)} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Field label="YTD SSNIT" value={fmtMoney(data.ytd?.ssnit)} /></Grid>
            </Grid>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button startIcon={<PictureAsPdf />} onClick={() => openBlob(`/payroll/payslips/${id}/pdf/`)}>Open PDF</Button>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
