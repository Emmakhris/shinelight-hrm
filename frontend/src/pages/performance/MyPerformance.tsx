import { Alert, Button, Card } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, StatusChip, useToast } from "../../components/Feedback";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { APPRAISAL_STATUS } from "./common";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function AppraisalTable({ rows, loading, showEmployee }: { rows: R[]; loading?: boolean; showEmployee?: boolean }) {
  const nav = useNavigate();
  return (
    <DataTable dense loading={loading} rows={rows} onRowClick={(r) => nav(`/performance/appraisals/${r.id}`)} emptyTitle="No appraisals"
      columns={[
        ...(showEmployee ? [{ key: "employee_name", label: "Employee", render: (r: R) => <><b>{r.employee_name}</b><br /><small>{r.job_title} · {r.department_name}</small></> }] : []),
        { key: "cycle_name", label: "Cycle" },
        { key: "template_name", label: "Form", hideOnMobile: true },
        ...(showEmployee ? [] : [{ key: "reviewer_name", label: "Reviewer", hideOnMobile: true }]),
        { key: "status", label: "Stage", render: (r) => <StatusChip value={r.status === "completed" ? "completed" : r.status === "cancelled" ? "cancelled" : "pending"} label={APPRAISAL_STATUS[r.status]} /> },
        { key: "final_rating_label", label: "Rating", render: (r) => (r.final_rating ? `${r.final_rating} – ${r.final_rating_label}` : "—") },
      ]} />
  );
}

export default function MyPerformance() {
  const aps = useApi<R>("/performance/appraisals/", { mine: 1 });
  const plans = useApi<R>("/performance/plans/", { mine: 1 });
  const [ack, setAck] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const myPlans = (plans.data?.results || []).filter((p: R) => p.is_mine);
  return (
    <>
      <PageHeader title="My performance" subtitle="Your objectives, reviews and development plans." />
      {(aps.data?.results || []).some((a: R) => ["objective_setting", "objectives_returned", "self_review", "acknowledgement"].includes(a.status)) &&
        <Alert severity="info" sx={{ mb: 2 }}>You have an appraisal step to complete. Open it below.</Alert>}
      <Card sx={{ mb: 2 }}><AppraisalTable rows={aps.data?.results || []} loading={aps.isLoading} /></Card>
      {myPlans.map((p: R) => (
        <Section key={p.id} title="Performance improvement plan" actions={!p.employee_acknowledged_at && ["active", "extended"].includes(p.status) && <Button variant="contained" onClick={() => setAck(p)}>Acknowledge</Button>}>
          <Field label="Period" value={`${fmtDate(p.start_date)} – ${fmtDate(p.end_date)}`} />
          <Field label="Areas to improve" value={p.reason} />
          <Field label="Support you will receive" value={p.support} />
          <DataTable dense rows={p.milestones} columns={[{ key: "objective", label: "Milestone" }, { key: "measure", label: "Measure" },
            { key: "due_date", label: "Due", render: (m) => fmtDate(m.due_date) }, { key: "status", label: "Progress", render: (m) => <StatusChip value={m.status} /> }]} />
          {p.status !== "active" && <Field label="Outcome" value={`${p.status} ${p.outcome_notes ? `– ${p.outcome_notes}` : ""}`} />}
        </Section>
      ))}
      <ConfirmDialog open={!!ack} title="Acknowledge improvement plan" comment="optional" confirmLabel="Acknowledge" onClose={() => setAck(null)}
        message="Acknowledging confirms you have received and discussed the plan. You may add your comments."
        onConfirm={async (comments) => { await post(`/performance/plans/${ack?.id}/acknowledge/`, { comments }); toast.ok("Acknowledged."); inv("/performance/"); }} />
    </>
  );
}
