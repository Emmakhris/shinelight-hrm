import { Alert, Box, Button, Grid2 as Grid, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { ExitInterviewForm } from "./ExitForms";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function ExitDetail() {
  const { id } = useParams();
  const { can, me } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const q = useApi<R>(`/offboarding/separations/${id}/`);
  const [clearing, setClearing] = useState<R | null>(null);
  const [dialog, setDialog] = useState<null | "extend" | "withdraw" | "interview">(null);
  if (q.isLoading) return <Loading />;
  const s = q.data;
  if (!s) return <ErrorAlert error={q.error} />;
  const manage = can("offboarding.manage");
  const refresh = () => inv("/offboarding/");
  const ei = s.exit_interview;
  return (
    <>
      <PageHeader title={`Exit: ${s.employee_name}`} subtitle={`${s.reference} · ${s.exit_type_label} · last working day ${fmtDate(s.last_working_day)}`}
        crumbs={[{ label: "Exits", to: "/offboarding" }, { label: s.employee_name }]}
        actions={<>
          <StatusChip value={s.status === "clearance" ? "in_progress" : s.status} label={s.status_label} />
          <Button component={RouterLink} to={`/employees/${s.employee}`}>Employee record</Button>
          {manage && s.status === "clearance" && <Button onClick={() => setDialog("extend")}>Extend access</Button>}
          {manage && s.status === "clearance" && ei && !ei.completed_at && <Button onClick={() => setDialog("interview")}>Record exit interview</Button>}
          {(manage || s.employee === me?.employee?.id) && ["pending", "returned", "clearance"].includes(s.status) && <Button color="error" onClick={() => setDialog("withdraw")}>Withdraw</Button>}
        </>} />
      {s.notice_shortfall_days > 0 && <Alert severity="warning" sx={{ mb: 2 }}>Notice is {s.notice_shortfall_days} day(s) short of the {s.notice_required_days} days required; payment in lieu may apply in the final pay.</Alert>}
      {s.access_extension_until && <Alert severity="info" sx={{ mb: 2 }}>System access extended to {fmtDate(s.access_extension_until)} (approved exception).</Alert>}
      {s.status === "completed" && <Alert severity="success" sx={{ mb: 2 }}>Clearance completed {fmtDate(s.completed_at)}.{s.certificate && " The certificate of service is in the personnel file."}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Details">
            <Stack spacing={1}>
              <Field label="Employee" value={`${s.employee_name} (${s.staff_number})`} />
              <Field label="Role" value={`${s.job_title || "—"} · ${s.department_name || ""}`} />
              <Field label="Reason" value={s.reason_label || "—"} />
              <Field label="Notice given" value={fmtDate(s.notice_date)} />
              <Field label="Rehire eligible" value={s.rehire_eligible ? "Yes" : "No"} />
              {s.handover_to_name && <Field label="Handover to" value={s.handover_to_name} />}
              {s.details && <Field label="Details" value={<span style={{ whiteSpace: "pre-wrap" }}>{s.details}</span>} />}
              {s.handover_notes && <Field label="Handover notes" value={s.handover_notes} />}
            </Stack>
          </Section>
          {ei?.completed_at && ei.ratings && <Section title="Exit interview">
            {Object.entries(ei.ratings).map(([k, v]) => <Field key={k} label={k} value={`${v} / 5`} />)}
            {ei.what_to_improve && <Field label="Improve" value={ei.what_to_improve} />}
            {ei.what_went_well && <Field label="Went well" value={ei.what_went_well} />}
          </Section>}
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <Section title="Clearance">
            {s.status !== "clearance" && s.clearance.length === 0 && <Typography color="text.secondary">Clearance opens once the exit is approved.</Typography>}
            {s.clearance.map((c: R) => (
              <Box key={c.id} sx={{ borderTop: "1px solid #eef0f3", py: 1 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                  <Box><b>{c.title}</b><br /><small>{c.owner_label}{c.cleared_by_name && ` · ${c.status} by ${c.cleared_by_name} ${fmtDate(c.cleared_at)}`}{c.notes && ` — ${c.notes}`}</small>
                    {c.check && <Typography variant="caption" display="block" color={c.check.ok ? "success.main" : "warning.main"}>{c.check.ok ? "✔" : "⚠"} {c.check.info}</Typography>}</Box>
                  <Stack direction="row" spacing={1}>
                    <StatusChip value={c.status === "pending" ? "pending" : "completed"} label={c.status} />
                    {c.can_clear && <Button size="small" variant="contained" onClick={() => setClearing(c)}>Clear</Button>}
                  </Stack>
                </Stack>
              </Box>))}
          </Section>
        </Grid>
      </Grid>
      <FormDialog open={!!clearing} title={`Clear: ${clearing?.title}`} onClose={() => setClearing(null)} initial={{ waive: false }}
        intro={clearing?.check && !clearing.check.ok ? <Alert severity="warning">{clearing.check.info}. {manage ? "HR can waive the item with a reason." : "Resolve this first."}</Alert> : undefined}
        fields={[{ name: "notes", label: "Notes", type: "textarea" }, ...(manage ? [{ name: "waive", label: "Waive this item (reason required)", type: "checkbox" as const }] : [])]}
        onSubmit={async (v) => { await post(`/offboarding/clearance/${clearing?.id}/clear/`, v); toast.ok("Cleared."); refresh(); }} />
      <FormDialog open={dialog === "extend"} title="Extend system access" onClose={() => setDialog(null)}
        intro={<Alert severity="info">An approved exception, e.g. to complete a handover. Access is revoked automatically after this date. Up to 30 days.</Alert>}
        fields={[{ name: "until", label: "Keep access until", type: "date", required: true }, { name: "reason", label: "Reason", type: "textarea", required: true }]}
        onSubmit={async (v) => { await post(`/offboarding/separations/${id}/extend-access/`, v); toast.ok("Access extended."); refresh(); }} />
      <ConfirmDialog open={dialog === "withdraw"} title="Withdraw this exit?" comment="optional" confirmLabel="Withdraw" color="error" onClose={() => setDialog(null)}
        message={s.status === "clearance" ? "The recorded exit date is removed and clearance cancelled." : undefined}
        onConfirm={async (reason) => { await post(`/offboarding/separations/${id}/withdraw/`, { reason }); toast.ok("Withdrawn."); refresh(); }} />
      {dialog === "interview" && <Section title="Exit interview (recorded by HR)"><ExitInterviewForm sep={s} onDone={() => setDialog(null)} /></Section>}
    </>
  );
}
