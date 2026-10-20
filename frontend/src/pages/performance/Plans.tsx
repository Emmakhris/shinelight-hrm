import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack } from "@mui/material";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const MS_STATUS = [["pending", "Pending"], ["met", "Met"], ["partly_met", "Partly met"], ["not_met", "Not met"]].map(([value, label]) => ({ value, label }));

function PlanDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useApi<R>(`/performance/plans/${id}/`);
  const toast = useToast();
  const inv = useInvalidate();
  const [ms, setMs] = useState<R | null>(null);
  const [closing, setClosing] = useState(false);
  const p = q.data;
  if (!p) return null;
  const draft = ["draft", "returned"].includes(p.status);
  const active = ["active", "extended"].includes(p.status);
  const refresh = () => inv("/performance/");
  const act = async (fn: () => Promise<unknown>, m: string) => { try { await fn(); toast.ok(m); refresh(); } catch (e) { toast.error(e); } };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Improvement plan — {p.employee_name} <StatusChip value={p.status} /></DialogTitle>
      <DialogContent>
        <Stack spacing={1.5}>
          <Field label="Period" value={`${fmtDate(p.start_date)} – ${fmtDate(p.end_date)} · progress review every ${p.review_frequency_days} days`} />
          <Field label="Performance gaps" value={p.reason} />
          <Field label="Support" value={p.support || "—"} />
          {p.employee_acknowledged_at && <Field label="Employee acknowledged" value={`${fmtDate(p.employee_acknowledged_at)}${p.employee_comments ? ` — ${p.employee_comments}` : ""}`} />}
          {p.outcome_notes && <Field label="Outcome" value={p.outcome_notes} />}
          <DataTable dense rows={p.milestones} emptyTitle="Add measurable milestones" columns={[
            { key: "objective", label: "Milestone" }, { key: "measure", label: "Measure" },
            { key: "due_date", label: "Due", render: (m) => fmtDate(m.due_date) },
            { key: "status", label: "Progress", render: (m) => <StatusChip value={m.status} /> },
            { key: "review_notes", label: "Notes", render: (m) => <small>{m.review_notes}</small> },
            { key: "_e", label: "", render: (m) => (draft || active) && <Button size="small" onClick={() => setMs(m)}>{draft ? "Edit" : "Update"}</Button> },
          ]} />
          {p.status === "returned" && <Alert severity="warning">HR returned this plan. See My requests for the comment.</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        {draft && <Button onClick={() => setMs({ plan: p.id })}>Add milestone</Button>}
        {draft && <Button variant="contained" onClick={() => act(() => post(`/performance/plans/${p.id}/submit/`), "Sent to HR for approval.")}>Submit to HR</Button>}
        {active && <Button variant="contained" onClick={() => setClosing(true)}>Record outcome</Button>}
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
      <FormDialog open={!!ms} title="Milestone" onClose={() => setMs(null)} initial={ms || undefined}
        fields={draft ? [{ name: "objective", label: "Milestone", required: true }, { name: "measure", label: "Measure", width: 8 },
          { name: "due_date", label: "Due", type: "date", required: true, width: 4 }]
          : [{ name: "status", label: "Progress", type: "select", options: MS_STATUS, required: true }, { name: "review_notes", label: "Review notes", type: "textarea" }]}
        onSubmit={async (d) => {
          const body = { ...(d as R), plan: p.id };
          if (ms?.id) await api.patch(`/performance/milestones/${ms.id}/`, body); else await api.post("/performance/milestones/", body);
          refresh();
        }} />
      <FormDialog open={closing} title="Record plan outcome" onClose={() => setClosing(false)} initial={{ outcome: "successful" }}
        intro={<Alert severity="info">Base the outcome on evidence for each milestone. An unsuccessful plan may lead to formal action under the conditions of service.</Alert>}
        fields={[{ name: "outcome", label: "Outcome", type: "select", required: true, options: [{ value: "successful", label: "Completed successfully" }, { value: "extended", label: "Extend the plan" }, { value: "unsuccessful", label: "Not successful" }] },
          { name: "new_end_date", label: "New end date", type: "date", hidden: (v) => v.outcome !== "extended" },
          { name: "notes", label: "Outcome and evidence", type: "textarea", required: true }]}
        onSubmit={async (d) => { await post(`/performance/plans/${p.id}/close/`, d); toast.ok("Outcome recorded."); refresh(); }} />
    </Dialog>
  );
}

export default function Plans() {
  const [params] = useSearchParams();
  const [open, setOpen] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  useEffect(() => { if (params.get("employee")) setCreating(true); }, [params]);
  return (
    <>
      <ResourcePage title="Performance improvement plans" url="/performance/plans/" canCreate={false} canEdit={false}
        subtitle="Structured support for staff below expectations: measurable milestones, support and regular reviews. HR approves each plan before it starts."
        headerActions={<Button variant="contained" onClick={() => setCreating(true)}>New plan</Button>}
        onRowClick={(r) => setOpen(r.id)}
        columns={[
          { key: "employee_name", label: "Employee", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.department_name}</small></> },
          { key: "supervisor_name", label: "Supervisor", hideOnMobile: true },
          { key: "period", label: "Period", render: (r) => `${fmtDate(r.start_date)} – ${fmtDate(r.end_date)}` },
          { key: "milestones", label: "Milestones", align: "right", render: (r) => `${r.milestones.filter((m: R) => m.status === "met").length}/${r.milestones.length} met` },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> },
        ]} />
      <FormDialog open={creating} title="New improvement plan" onClose={() => setCreating(false)} maxWidth="md"
        initial={{ employee: params.get("employee") ? Number(params.get("employee")) : "", appraisal: params.get("appraisal") ? Number(params.get("appraisal")) : null, review_frequency_days: 14 }}
        intro={<Alert severity="info">Start as a draft, add milestones, then submit to HR. The employee sees the plan once HR approves it. Plans should run at least 30 days.</Alert>}
        fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", required: true },
          { name: "start_date", label: "Start", type: "date", required: true, width: 4 }, { name: "end_date", label: "End", type: "date", required: true, width: 4 },
          { name: "review_frequency_days", label: "Review every (days)", type: "number", width: 4 },
          { name: "reason", label: "Performance gaps, with evidence", type: "textarea", required: true },
          { name: "support", label: "Support: training, coaching, resources", type: "textarea", required: true }]}
        onSubmit={async (d) => {
          const r = await api.post<R>("/performance/plans/", { ...(d as R), appraisal: params.get("appraisal") ? Number(params.get("appraisal")) : null });
          toast.ok("Draft created. Add milestones, then submit."); inv("/performance/"); setOpen(r.data.id);
        }} />
      {open && <PlanDialog id={open} onClose={() => setOpen(null)} />}
    </>
  );
}
