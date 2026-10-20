import AccountBalance from "@mui/icons-material/AccountBalance";
import Calculate from "@mui/icons-material/Calculate";
import Download from "@mui/icons-material/Download";
import LockOpen from "@mui/icons-material/LockOpen";
import Send from "@mui/icons-material/Send";
import Undo from "@mui/icons-material/Undo";
import { Alert, Button, Card, Grid2 as Grid, MenuItem, Stack, Step, StepLabel, Stepper, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { download } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { PayslipDialog } from "../../components/PayslipView";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime, fmtMoney } from "../../utils";

type Run = Record<string, unknown> & { totals: Record<string, string>; status: string };
const STEPS = ["draft", "calculated", "submitted", "approved", "paid"];
const REPORTS = [["register", "Payroll register"], ["variance", "Variance vs last period"], ["paye", "GRA PAYE schedule"],
  ["ssnit", "SSNIT contribution report"], ["journal", "GL journal"]];

export default function RunDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const run = useApi<Run>(`/payroll/runs/${id}/`);
  const [tab, setTab] = useState("payslips");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [slip, setSlip] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<null | "submit" | "release" | "reverse">(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const slips = useApi<{ count: number; results: Record<string, unknown>[] }>(tab === "payslips" ? `/payroll/runs/${id}/payslips/` : null, { status, search, page });
  const report = useApi<{ headers: string[]; rows: unknown[][]; money_columns: number[] }>(REPORTS.some(([k]) => k === tab) ? `/payroll/runs/${id}/report/${tab}/` : null);
  if (run.isLoading) return <Loading />;
  if (run.error || !run.data) return <ErrorAlert error={run.error} />;
  const r = run.data;
  const t = r.totals || {};
  const act = async (path: string, body?: unknown, msg?: string) => {
    setBusy(true); setErr(null);
    try { await post(`/payroll/runs/${id}/${path}/`, body); toast.ok(msg || "Done."); inv("/payroll/", "/workflow/"); }
    catch (e) { setErr(e); throw e; } finally { setBusy(false); }
  };
  const editable = ["draft", "calculated", "rejected"].includes(r.status);
  return (
    <>
      <PageHeader title={`Payroll — ${r.period_name}`} subtitle={`${r.run_type_label} run #${r.number} · pay date ${fmtDate(r.pay_date as string)}${r.status === "reversed" ? " · REVERSED" : ""}`}
        crumbs={[{ label: "Payroll runs", to: "/payroll/runs" }, { label: String(r.period_name) }]}
        actions={<>
          {editable && can("payroll.prepare") && <Button variant="contained" startIcon={<Calculate />} disabled={busy}
            onClick={() => act("calculate", undefined, "Payroll calculated.").catch(() => undefined)}>{r.status === "draft" ? "Calculate" : "Recalculate"}</Button>}
          {r.status === "calculated" && can("payroll.prepare") && <Button variant="contained" color="secondary" startIcon={<Send />} onClick={() => setConfirm("submit")}>Submit for approval</Button>}
          {r.status === "approved" && can("payroll.release") && <>
            <Button startIcon={<AccountBalance />} onClick={() => download(`/payroll/runs/${id}/bank-file/`, { format: "csv" })}>Bank file</Button>
            <Button startIcon={<AccountBalance />} onClick={() => download(`/payroll/runs/${id}/bank-file/`, { method: "momo", format: "csv" })}>MoMo file</Button>
            <Button variant="contained" color="success" startIcon={<LockOpen />} onClick={() => setConfirm("release")}>Release & publish payslips</Button>
          </>}
          {r.status === "paid" && can("payroll.release") && <>
            <Button startIcon={<AccountBalance />} onClick={() => download(`/payroll/runs/${id}/bank-file/`, { format: "csv" })}>Bank file</Button>
            <Button color="error" startIcon={<Undo />} onClick={() => setConfirm("reverse")}>Reverse</Button>
          </>}
        </>} />
      <ErrorAlert error={err} />
      <Card sx={{ p: 2, mb: 2 }}>
        <Stepper activeStep={r.status === "rejected" ? 1 : r.status === "paid" || r.status === "reversed" ? STEPS.length : STEPS.indexOf(r.status)} alternativeLabel>
          {["Draft", "Calculated", "Submitted", "Approved", "Released"].map((l) => <Step key={l}><StepLabel>{l}</StepLabel></Step>)}
        </Stepper>
        <Stack direction="row" spacing={3} sx={{ mt: 2, fontSize: 13, color: "text.secondary" }} flexWrap="wrap" useFlexGap>
          {!!r.calculated_by_name && <span>Prepared by {String(r.calculated_by_name)} · {fmtDateTime(r.calculated_at as string)} (×{String(r.calculation_count)})</span>}
          {!!r.approved_by_name && <span>Approved by {String(r.approved_by_name)} · {fmtDateTime(r.approved_at as string)}</span>}
          {!!r.released_by_name && <span>Released by {String(r.released_by_name)} · {fmtDateTime(r.released_at as string)}</span>}
        </Stack>
      </Card>
      {r.status === "rejected" && <Alert severity="warning" sx={{ mb: 2 }}>The approver returned this payroll. Review the comments in the request history, fix, and recalculate.</Alert>}
      {t.warning && <Alert severity="warning" sx={{ mb: 2 }}>{t.warning} Confirm PAYE bands and SSNIT rates under Payroll setup.</Alert>}
      {t.employees !== undefined && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          {[["Employees", t.employees], ["Gross pay", fmtMoney(t.gross)], ["PAYE (incl. bonus/OT tax)", fmtMoney(Number(t.paye) + Number(t.bonus_tax || 0) + Number(t.overtime_tax || 0))],
            ["SSNIT (employee + employer)", fmtMoney(Number(t.ssnit_employee) + Number(t.ssnit_employer))], ["Net pay", fmtMoney(t.net)], ["Employer cost", fmtMoney(t.employer_cost)]].map(([l, v]) => (
            <Grid key={l} size={{ xs: 6, md: 2 }}><Kpi label={String(l)} value={String(v)} /></Grid>
          ))}
          <Grid size={12}>
            <Stack direction="row" spacing={1}>
              {Number(t.errors) > 0 && <Button color="error" variant="outlined" onClick={() => { setTab("payslips"); setStatus("error"); }}>{t.errors} errors</Button>}
              {Number(t.warnings) > 0 && <Button color="warning" variant="outlined" onClick={() => { setTab("payslips"); setStatus("warning"); }}>{t.warnings} warnings</Button>}
              {Number(t.on_hold) > 0 && <Button variant="outlined" onClick={() => { setTab("payslips"); setStatus("hold"); }}>{t.on_hold} on hold</Button>}
            </Stack>
          </Grid>
        </Grid>
      )}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ mb: 2 }}>
        <Tab value="payslips" label="Payslips" />
        {REPORTS.map(([k, l]) => <Tab key={k} value={k} label={l} />)}
        {editable && <Tab value="adjustments" label="One-off adjustments" />}
      </Tabs>
      {tab === "payslips" && (
        <Card>
          <Stack direction="row" spacing={1} sx={{ p: 1.5 }}>
            <TextField placeholder="Search name / staff no" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
            <TextField select label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} sx={{ minWidth: 140 }}>
              <MenuItem value="">All</MenuItem>{["ok", "warning", "error", "hold"].map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </TextField>
          </Stack>
          <DataTable dense loading={slips.isLoading} rows={slips.data?.results || []} onRowClick={(s) => setSlip(s.id as number)}
            count={slips.data?.count} page={page} onPageChange={setPage} emptyTitle={r.status === "draft" ? "Calculate the payroll to see payslips" : undefined}
            columns={[
              { key: "staff_number", label: "Staff no" }, { key: "employee_name", label: "Name" }, { key: "department", label: "Department", hideOnMobile: true },
              { key: "days_payable", label: "Days", align: "right", render: (s) => Number(s.days_payable) },
              { key: "gross_pay", label: "Gross", align: "right", render: (s) => fmtMoney(s.gross_pay as string, "") },
              { key: "paye", label: "PAYE", align: "right", render: (s) => fmtMoney(s.paye as string, "") },
              { key: "ssnit_employee", label: "SSNIT", align: "right", render: (s) => fmtMoney(s.ssnit_employee as string, ""), hideOnMobile: true },
              { key: "total_deductions", label: "Deductions", align: "right", render: (s) => fmtMoney(s.total_deductions as string, ""), hideOnMobile: true },
              { key: "net_pay", label: "Net", align: "right", render: (s) => <b>{fmtMoney(s.net_pay as string, "")}</b> },
              { key: "status", label: "", render: (s) => s.status !== "ok" ? <StatusChip value={s.status as string} /> : null },
              { key: "messages", label: "Notes", render: (s) => (s.messages as string[]).join(" • "), hideOnMobile: true },
            ]} />
        </Card>
      )}
      {REPORTS.some(([k]) => k === tab) && (
        <Card>
          <Stack direction="row" justifyContent="flex-end" sx={{ p: 1 }}>
            <Button startIcon={<Download />} onClick={() => download(`/payroll/runs/${id}/report/${tab}/`, { format: "xlsx" })}>Excel</Button>
            <Button startIcon={<Download />} onClick={() => download(`/payroll/runs/${id}/report/${tab}/`, { format: "csv" })}>CSV</Button>
          </Stack>
          <DataTable dense loading={report.isLoading}
            rows={(report.data?.rows || []).map((row, i) => Object.fromEntries([["id", i], ...row.map((v, j) => [`c${j}`, v])]))}
            columns={(report.data?.headers || []).map((h, j) => {
              const money = report.data?.money_columns.includes(j);
              return { key: `c${j}`, label: h, align: money ? "right" as const : undefined,
                render: money ? (row: Record<string, unknown>) => fmtMoney(row[`c${j}`] as string, "") : undefined };
            })} />
        </Card>
      )}
      {tab === "adjustments" && (
        <Card><ResourcePage embedded title="Adjustment" url="/payroll/adjustments/" params={{ period: r.period as number }} canDelete writePerm="payroll.prepare"
          intro="Arrears, bonuses, commissions and one-off recoveries for this period. Recalculate after changes."
          columns={[{ key: "employee_name", label: "Employee" }, { key: "element_name", label: "Element" },
            { key: "amount", label: "Amount", align: "right", render: (a) => fmtMoney(a.amount as string) }, { key: "reason", label: "Reason" },
            { key: "is_system", label: "Auto", render: (a) => (a.is_system ? "Yes" : "") }]}
          fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})`, required: true },
            { name: "element", label: "Pay element", type: "ref", ref: "/payroll/elements/", refLabel: (e) => `${e.code} — ${e.name}`, required: true },
            { name: "amount", label: "Amount (GHS)", type: "number", required: true, width: 6 }, { name: "quantity", label: "Quantity (hours/days)", type: "number", width: 6 },
            { name: "reason", label: "Reason", required: true }, { name: "period", label: "", hidden: () => true }]}
          defaults={{ period: r.period }} createLabel="Add adjustment" /></Card>
      )}
      <PayslipDialog id={slip} onClose={() => setSlip(null)} showDiagnostics />
      <ConfirmDialog open={confirm === "submit"} onClose={() => setConfirm(null)} title="Submit payroll for approval?" confirmLabel="Submit"
        message={`Net pay ${fmtMoney(t.net)} for ${t.employees} employees. The run is locked while under review.`} onConfirm={() => act("submit", undefined, "Submitted to the payroll approver.")} />
      <ConfirmDialog open={confirm === "release"} onClose={() => setConfirm(null)} title="Release payroll?" color="success" confirmLabel="Release"
        message="This locks the run and attendance for the period, posts loan repayments, and publishes payslips to employees. Upload the bank file to your bank first."
        onConfirm={() => act("release", { publish: true }, "Payroll released and payslips published.")} />
      <ConfirmDialog open={confirm === "reverse"} onClose={() => setConfirm(null)} title="Reverse released payroll?" color="error" confirmLabel="Reverse" comment="required"
        message="A reversal run negating every payslip is created and loan balances are restored. Use only for serious errors (e.g. a wrong bank file)."
        onConfirm={(c) => act("reverse", { reason: c }, "Reversal run created.")} />
    </>
  );
}
