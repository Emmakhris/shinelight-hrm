import { Alert, Button, Card, Checkbox, Grid2 as Grid, TextField } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function ReviewDetail() {
  const { id } = useParams();
  const { can, me } = useAuth();
  const cycle = useApi<R>(`/compensation/reviews/${id}/`);
  const lines = useApi<R[]>(`/compensation/reviews/${id}/lines/`);
  const [confirm, setConfirm] = useState<null | "submit" | "apply">(null);
  const [err, setErr] = useState<unknown>(null);
  const inv = useInvalidate();
  const toast = useToast();
  if (cycle.isLoading) return <Loading />;
  if (!cycle.data) return <ErrorAlert error={cycle.error} />;
  const c = cycle.data;
  const s = c.summary;
  const editable = ["open", "returned"].includes(c.status) && can("compensation.manage");
  const patch = async (line: R, data: R) => {
    setErr(null);
    try { await api.patch(`/compensation/reviews/${id}/lines/${line.id}/`, data); inv(`/compensation/reviews/${id}`); }
    catch (e) { setErr(e); }
  };
  return (
    <>
      <PageHeader title={c.name} subtitle={`Effective ${fmtDate(c.effective_date)}`} crumbs={[{ label: "Salary reviews", to: "/compensation/reviews" }, { label: c.name }]}
        actions={<>
          <StatusChip value={c.status} />
          {["draft", "open", "returned"].includes(c.status) && can("compensation.manage") &&
            <Button onClick={async () => { const r = await post<{ added: number }>(`/compensation/reviews/${id}/populate/`); toast.ok(`${r.added} employee(s) added.`); inv("/compensation/"); }}>Add eligible staff</Button>}
          {editable && <Button variant="contained" onClick={() => setConfirm("submit")}>Submit for approval</Button>}
          {c.status === "approved" && can("compensation.manage") && <Button variant="contained" color="success" onClick={() => setConfirm("apply")}>Apply salary changes</Button>}
        </>} />
      <ErrorAlert error={err} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Employees", s.employees], ["Current monthly payroll", fmtMoney(s.current_monthly)], ["Monthly increase", fmtMoney(s.monthly_increase)],
          ["Annual cost", fmtMoney(s.annual_increase)], ["Average increase", `${s.average_percent}%`],
          ["Budget", Number(c.budget_percent) ? `${fmtMoney(s.budget_monthly)}/month` : "—"]].map(([l, v]) => (
          <Grid key={l} size={{ xs: 6, md: 2 }}><Kpi label={l} value={v} color={l === "Budget" && !s.within_budget ? "#b91c1c" : undefined} /></Grid>
        ))}
      </Grid>
      {!s.within_budget && <Alert severity="warning" sx={{ mb: 2 }}>Proposals exceed the approved budget.</Alert>}
      {s.missing_justification > 0 && <Alert severity="warning" sx={{ mb: 2 }}>{s.missing_justification} proposal(s) outside the guideline need a justification.</Alert>}
      <Card>
        <DataTable dense loading={lines.isLoading} rows={lines.data || []} columns={[
          { key: "employee_name", label: "Employee" }, { key: "department", label: "Department", hideOnMobile: true }, { key: "grade", label: "Grade" },
          { key: "current_basic", label: "Current", align: "right", render: (r) => fmtMoney(r.current_basic, "") },
          { key: "guideline", label: "Guide", render: (r) => (r.guideline ? `${Number(r.guideline.min)}–${Number(r.guideline.max)}%` : "—") },
          { key: "increase_percent", label: "Increase %", render: (r) => editable && r.employee !== me?.employee?.id ? (
            <TextField key={`${r.id}-${r.increase_percent}`} defaultValue={Number(r.increase_percent)} type="number" sx={{ width: 90 }}
              error={r.outside_guideline} onBlur={(e) => Number(e.target.value) !== Number(r.increase_percent) && patch(r, { increase_percent: e.target.value })} />
          ) : `${Number(r.increase_percent)}%` },
          { key: "proposed_basic", label: "Proposed", align: "right", render: (r) => <b>{fmtMoney(r.proposed_basic, "")}</b> },
          { key: "justification", label: "Justification", render: (r) => editable ? (
            <TextField key={`j${r.id}`} defaultValue={r.justification} placeholder={r.outside_guideline ? "Required" : ""} error={r.outside_guideline && !r.justification}
              onBlur={(e) => e.target.value !== r.justification && patch(r, { justification: e.target.value })} sx={{ minWidth: 180 }} />
          ) : r.justification },
          { key: "excluded", label: "Exclude", render: (r) => <Checkbox checked={r.excluded} disabled={!editable} onChange={(e) => patch(r, { excluded: e.target.checked })} /> },
          { key: "applied", label: "", render: (r) => (r.applied ? "Applied" : "") },
        ]} />
      </Card>
      <ConfirmDialog open={confirm === "submit"} onClose={() => setConfirm(null)} title="Submit salary review for approval?" confirmLabel="Submit"
        message={`Annual cost ${fmtMoney(s.annual_increase)} for ${s.employees} employees.`}
        onConfirm={async () => { await post(`/compensation/reviews/${id}/submit/`); toast.ok("Submitted."); inv("/compensation/"); }} />
      <ConfirmDialog open={confirm === "apply"} onClose={() => setConfirm(null)} title="Apply approved salary changes?" color="success" confirmLabel="Apply"
        message="Each increase is recorded as a salary-change personnel action effective from the review date. Payroll picks it up automatically; back-dated changes appear as arrears."
        onConfirm={async () => { const r = await post<{ detail: string }>(`/compensation/reviews/${id}/apply/`); toast.ok(r.detail); inv("/compensation/", "/employees"); }} />
    </>
  );
}
