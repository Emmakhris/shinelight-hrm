import { Alert, Box, Button, Grid2 as Grid, Stack } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function IncidentDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const q = useApi<R>(`/safety/incidents/${id}/`);
  const [dialog, setDialog] = useState<null | "investigate" | "action">(null);
  if (q.isLoading) return <Loading />;
  const i = q.data;
  if (!i) return <ErrorAlert error={q.error} />;
  const manage = can("ohs.manage");
  const refresh = () => inv("/safety/");
  const act = async (fn: () => Promise<unknown>, m: string) => { try { await fn(); toast.ok(m); refresh(); } catch (e) { toast.error(e); } };
  return (
    <>
      <PageHeader title={`${i.reference} — ${i.kind_label}`} subtitle={`${fmtDateTime(i.occurred_at)} · ${i.location} · ${i.severity_label}`}
        crumbs={[{ label: "Health & safety", to: "/safety" }, { label: i.reference }]}
        actions={<>
          <StatusChip value={i.status === "closed" ? "completed" : "in_progress"} label={i.status_label} />
          {manage && i.status !== "closed" && <><Button onClick={() => setDialog("investigate")}>Investigation</Button><Button onClick={() => setDialog("action")}>Add action</Button>
            <Button variant="contained" onClick={() => act(() => post(`/safety/incidents/${id}/close/`), "Incident closed.")}>Close</Button></>}
        </>} />
      {i.kind === "exposure" && <Alert severity="warning" sx={{ mb: 2 }}>Occupational exposure: occupational health has been alerted for confidential follow-up (post-exposure prophylaxis is time-critical).</Alert>}
      {i.reportable && !i.reported_to_authority_on && <Alert severity="error" sx={{ mb: 2 }}>Reportable incident: record when it was notified to the Labour Department / Factories Inspectorate.</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="What happened">
            <Stack spacing={1}>
              <Field label="Description" value={<span style={{ whiteSpace: "pre-wrap" }}>{i.description}</span>} />
              {i.immediate_action && <Field label="Immediate action" value={i.immediate_action} />}
              <Field label="Staff involved" value={i.persons.map((p: R) => p.name).join(", ") || "—"} />
              {i.others_involved && <Field label="Others involved" value={i.others_involved} />}
              <Field label="Department" value={i.department_name || "—"} />
              <Field label="Reported by" value={i.reported_by_name || "—"} />
            </Stack>
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="Investigation">
            <Stack spacing={1}>
              <Field label="Investigator" value={i.investigator_name || "Not assigned"} />
              <Field label="Root cause" value={i.root_cause || "—"} />
              {i.contributing_factors && <Field label="Contributing factors" value={i.contributing_factors} />}
              <Field label="Lost time" value={`${i.lost_time_days} day(s)`} />
              <Field label="Reportable" value={i.reportable ? `Yes${i.reported_to_authority_on ? `, notified ${fmtDate(i.reported_to_authority_on)}` : " — not yet notified"}` : "No"} />
            </Stack>
          </Section>
          <Section title="Corrective actions">
            {i.actions.length === 0 && <Box color="text.secondary">No actions yet.</Box>}
            {i.actions.map((a: R) => (
              <Stack key={a.id} direction="row" justifyContent="space-between" alignItems="center" sx={{ borderTop: "1px solid #eef0f3", py: 1 }}>
                <Box>{a.description}<br /><small>{a.owner_name} · due {fmtDate(a.due_date)}{a.notes && ` · ${a.notes}`}</small></Box>
                {a.status === "open" ? <Button size="small" onClick={() => act(() => post(`/safety/actions/${a.id}/complete/`, {}), "Done.")}>Mark done</Button> : <StatusChip value="completed" label={a.status} />}
              </Stack>))}
          </Section>
        </Grid>
      </Grid>
      <FormDialog open={dialog === "investigate"} title="Investigation" onClose={() => setDialog(null)}
        initial={{ root_cause: i.root_cause, contributing_factors: i.contributing_factors, lost_time_days: i.lost_time_days, reportable: i.reportable, reported_to_authority_on: i.reported_to_authority_on }}
        fields={[{ name: "investigator", label: "Investigator", type: "ref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name || u.username) },
          { name: "root_cause", label: "Root cause", type: "textarea" }, { name: "contributing_factors", label: "Contributing factors", type: "textarea" },
          { name: "lost_time_days", label: "Lost-time days", type: "number", width: 4 }, { name: "reportable", label: "Reportable to authority", type: "checkbox", width: 4 },
          { name: "reported_to_authority_on", label: "Notified on", type: "date", width: 4 }]}
        onSubmit={async (v) => { await post(`/safety/incidents/${id}/investigate/`, v); toast.ok("Saved."); refresh(); }} />
      <FormDialog open={dialog === "action"} title="Corrective action" onClose={() => setDialog(null)}
        fields={[{ name: "description", label: "Action", type: "textarea", required: true },
          { name: "owner", label: "Owner", type: "ref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name || u.username), required: true, width: 6 },
          { name: "due_date", label: "Due", type: "date", required: true, width: 6 }]}
        onSubmit={async (v) => { await post(`/safety/incidents/${id}/add-action/`, v); toast.ok("Action added."); refresh(); }} />
    </>
  );
}
