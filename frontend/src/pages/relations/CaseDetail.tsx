import { Alert, Box, Button, Grid2 as Grid, List, ListItem, ListItemText, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, openBlob } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const opts = (p: string[][]) => p.map(([value, label]) => ({ value, label }));
const OUTCOMES = opts([["no_case", "No case to answer"], ["resolved_informally", "Resolved informally"], ["mediation_agreement", "Mediation agreement"],
  ["counselling", "Counselling"], ["verbal_warning", "Verbal warning"], ["written_warning", "Written warning"], ["final_warning", "Final written warning"],
  ["suspension", "Suspension"], ["demotion", "Demotion"], ["dismissal", "Dismissal"], ["upheld", "Grievance upheld"], ["not_upheld", "Grievance not upheld"], ["other", "Other"]]);
const SANCTIONS = ["verbal_warning", "written_warning", "final_warning", "suspension", "demotion", "dismissal", "counselling"];

export default function CaseDetail() {
  const { id } = useParams();
  const toast = useToast();
  const inv = useInvalidate();
  const q = useApi<R>(`/relations/cases/${id}/`);
  const [dialog, setDialog] = useState<null | "assign" | "note" | "meeting" | "decide" | "close">(null);
  const [minutes, setMinutes] = useState<R | null>(null);
  const [appeal, setAppeal] = useState<R | null>(null);
  if (q.isLoading) return <Loading />;
  const c = q.data;
  if (!c) return <ErrorAlert error={q.error} />;
  const refresh = () => inv("/relations/");
  const open = ["reported", "investigating", "hearing"].includes(c.status);
  const appeals = c.actions.flatMap((a: R) => a.appeals.map((ap: R) => ({ ...ap, action: a })));
  return (
    <>
      <PageHeader title={`${c.reference} — ${c.title}`} subtitle={`${c.case_type_label} · ${c.severity} · officer ${c.case_officer_name || "unassigned"} · due ${fmtDate(c.due_date)}`}
        crumbs={[{ label: "Employee relations", to: "/relations" }, { label: c.reference }]}
        actions={<>
          <StatusChip value={c.status === "closed" ? "completed" : "in_progress"} label={c.status_label} />
          {(c.is_senior || c.is_officer) && open && <Button onClick={() => setDialog("assign")}>Assign / plan</Button>}
          {c.status !== "closed" && <Button onClick={() => setDialog("note")}>Add note / evidence</Button>}
          {open && <Button onClick={() => setDialog("meeting")}>Schedule meeting</Button>}
          {open && <Button variant="contained" onClick={() => setDialog("decide")}>Record decision</Button>}
          {["decided"].includes(c.status) && <Button onClick={() => setDialog("close")}>Close case</Button>}
        </>} />
      <Alert severity="warning" sx={{ mb: 2 }}>Strictly confidential. Do not discuss with anyone not assigned to this case. Your access is recorded.</Alert>
      {c.overdue && <Alert severity="error" sx={{ mb: 2 }}>Past its resolution deadline.</Alert>}
      {c.status === "pending_decision" && <Alert severity="info" sx={{ mb: 2 }}>The decision includes a serious sanction and is awaiting HR Director approval.</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Section title="Case">
            <Stack spacing={1}>
              <Field label="Complainant" value={c.complainant_name || "—"} />
              <Field label="Reported by" value={`${c.reporter_name || "—"} · ${fmtDate(c.created_at)}`} />
              <Field label="Respondent(s)" value={c.respondent_names.join(", ") || "—"} />
              {c.incident_date && <Field label="Incident date" value={fmtDate(c.incident_date)} />}
              {c.policy_reference && <Field label="Policy" value={c.policy_reference} />}
              <Field label="Allegation" value={<span style={{ whiteSpace: "pre-wrap" }}>{c.description}</span>} />
              <Field label="Investigators" value={c.investigators.map((i: R) => i.name).join(", ") || "—"} />
              {c.investigation_plan && <Field label="Investigation plan" value={c.investigation_plan} />}
              {c.outcome && <Field label="Outcome" value={`${c.outcome_label}: ${c.outcome_summary}`} />}
            </Stack>
          </Section>
          <Section title="Meetings">
            {c.meetings.length === 0 && <Typography color="text.secondary">No meetings yet. A hearing must be held and minuted before any formal sanction.</Typography>}
            {c.meetings.map((m: R) => (
              <Box key={m.id} sx={{ borderTop: "1px solid #eef0f3", py: 1 }}>
                <Stack direction="row" justifyContent="space-between"><b>{m.kind} · {fmtDateTime(m.scheduled_at)}</b>
                  {!m.held && <Button size="small" onClick={() => setMinutes(m)}>Record minutes</Button>}</Stack>
                <small>{m.venue} · {m.invitee_names.join(", ")}{m.attendees && ` · ${m.attendees}`}</small>
                {m.minutes && <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", mt: 0.5 }}>{m.minutes}</Typography>}
              </Box>))}
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          {c.actions.length > 0 && <Section title="Outcomes issued">
            {c.actions.map((a: R) => (
              <Box key={a.id} sx={{ borderTop: "1px solid #eef0f3", py: 1 }}>
                <b>{a.action_label}</b> — {a.employee_name} · effective {fmtDate(a.effective_date)}{a.expires_on && ` · until ${fmtDate(a.expires_on)}`}
                {!a.issued_at && <small> (awaiting approval)</small>}
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{a.details}</Typography>
                {a.employee_response && <small>Employee response: {a.employee_response}</small>}
              </Box>))}
          </Section>}
          {appeals.length > 0 && <Section title="Appeals">
            {appeals.map((ap: R) => (
              <Box key={ap.id} sx={{ py: 1 }}>
                <b>{ap.action.employee_name}</b> appealed {ap.action.action_label.toLowerCase()} on {fmtDate(ap.created_at)}: {ap.grounds}
                <br /><StatusChip value={ap.status === "submitted" ? "pending" : "completed"} label={ap.status} /> {ap.decision}
                {c.is_senior && !c.is_officer && ap.status === "submitted" && <Button size="small" sx={{ ml: 1 }} onClick={() => setAppeal(ap)}>Decide appeal</Button>}
              </Box>))}
          </Section>}
          <Section title="Case file">
            <List dense>
              {c.notes.map((n: R) => (
                <ListItem key={n.id} disableGutters secondaryAction={n.has_file && <Button size="small" onClick={() => openBlob(`/relations/cases/${id}/evidence/${n.id}/`)}>{n.file_name}</Button>}>
                  <ListItemText primary={<><b>{n.kind}</b> {n.text}</>} secondary={`${fmtDateTime(n.created_at)} · ${n.author_name}`} />
                </ListItem>))}
              {c.notes.length === 0 && <Typography color="text.secondary">No notes yet.</Typography>}
            </List>
          </Section>
        </Grid>
      </Grid>
      <FormDialog open={dialog === "assign"} title="Assignment and investigation plan" onClose={() => setDialog(null)}
        initial={{ case_officer: c.case_officer, investigators: c.investigators.map((i: R) => i.id), investigation_plan: c.investigation_plan }}
        fields={[...(c.is_senior ? [{ name: "case_officer", label: "Case officer", type: "ref" as const, ref: "/users/lookup/", refLabel: (u: R) => String(u.full_name || u.username) }] : []),
          { name: "investigators", label: "Investigators", type: "multiref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name || u.username) },
          { name: "investigation_plan", label: "Investigation plan (witnesses, evidence, timeline)", type: "textarea" }]}
        onSubmit={async (v) => { await post(`/relations/cases/${id}/assign/`, v); toast.ok("Saved."); refresh(); }} />
      <FormDialog open={dialog === "note"} title="Add to the case file" onClose={() => setDialog(null)} initial={{ kind: "note" }}
        fields={[{ name: "kind", label: "Type", type: "select", options: opts([["note", "Case note"], ["finding", "Investigation finding"], ["statement", "Statement"], ["evidence", "Evidence"], ["correspondence", "Correspondence"]]) },
          { name: "text", label: "Text", type: "textarea" }, { name: "file", label: "Attach file", type: "file" }]}
        onSubmit={async (v) => { await api.post(`/relations/cases/${id}/note/`, v); toast.ok("Added."); refresh(); }} />
      <FormDialog open={dialog === "meeting"} title="Schedule meeting" onClose={() => setDialog(null)} initial={{ kind: "interview", invitees: [] }}
        intro={<Alert severity="info">Invitees receive a neutral notice (no case details) and are told they may bring a colleague or representative.</Alert>}
        fields={[{ name: "kind", label: "Type", type: "select", options: opts([["interview", "Investigation interview"], ["hearing", "Disciplinary hearing"], ["mediation", "Mediation"], ["appeal", "Appeal hearing"], ["other", "Other"]]), width: 6 },
          { name: "scheduled_at", label: "Date and time", type: "datetime", required: true, width: 6 }, { name: "venue", label: "Venue" },
          { name: "invitees", label: "Invite (employees)", type: "multiref", ref: "/employees/", refLabel: (e) => String(e.full_name) },
          { name: "attendees", label: "Panel / other attendees", type: "textarea" }]}
        onSubmit={async (v) => { await post(`/relations/cases/${id}/meeting/`, { ...(v as R), scheduled_at: new Date((v as R).scheduled_at).toISOString() }); toast.ok("Meeting scheduled."); refresh(); }} />
      <FormDialog open={!!minutes} title="Meeting minutes" onClose={() => setMinutes(null)}
        fields={[{ name: "minutes", label: "Minutes (who attended, what was said, evidence considered)", type: "textarea", required: true }]}
        onSubmit={async (v) => { await post(`/relations/cases/${id}/minutes/${minutes?.id}/`, v); toast.ok("Minutes recorded."); refresh(); }} />
      <FormDialog open={dialog === "decide"} title="Record decision" maxWidth="md" onClose={() => setDialog(null)}
        initial={{ outcome: "no_case", effective_date: new Date().toISOString().slice(0, 10), respondent: c.respondents[0] }}
        intro={<Alert severity="info">Formal sanctions need a minuted hearing first. Suspension, demotion and dismissal go to the HR Director for approval. Outcome letters go to the restricted personnel file and the employee can appeal within 14 days.</Alert>}
        fields={[{ name: "outcome", label: "Outcome", type: "select", required: true, options: OUTCOMES },
          { name: "summary", label: "Reasons for the decision", type: "textarea", required: true },
          { name: "respondent", label: "Sanction applies to", type: "select", hidden: (v) => !SANCTIONS.includes(String(v.outcome)),
            options: c.respondents.map((rid: number, i: number) => ({ value: rid, label: c.respondent_names[i] })) },
          { name: "effective_date", label: "Effective date", type: "date", width: 6, hidden: (v) => !SANCTIONS.includes(String(v.outcome)) },
          { name: "suspension_days", label: "Suspension (days)", type: "number", width: 6, hidden: (v) => v.outcome !== "suspension" }]}
        onSubmit={async (v) => {
          const d = v as R;
          const actions = SANCTIONS.includes(d.outcome) ? [{ employee: d.respondent, action_type: d.outcome, details: d.summary, effective_date: d.effective_date, suspension_days: d.suspension_days }] : [];
          await post(`/relations/cases/${id}/decide/`, { outcome: d.outcome, summary: d.summary, actions });
          toast.ok("Decision recorded."); refresh();
        }} />
      <FormDialog open={!!appeal} title="Decide appeal" onClose={() => setAppeal(null)} initial={{ status: "dismissed" }}
        fields={[{ name: "status", label: "Decision", type: "select", required: true, options: opts([["upheld", "Appeal upheld (sanction rescinded)"], ["varied", "Sanction varied"], ["dismissed", "Appeal dismissed"]]) },
          { name: "decision", label: "Reasons", type: "textarea", required: true }]}
        onSubmit={async (v) => { await post(`/relations/appeals/${appeal?.id}/decide/`, v); toast.ok("Appeal decided."); refresh(); }} />
      <ConfirmDialog open={dialog === "close"} title="Close the case?" comment="optional" confirmLabel="Close case" onClose={() => setDialog(null)}
        onConfirm={async (note) => { await post(`/relations/cases/${id}/close/`, { note }); toast.ok("Closed."); refresh(); }} />
    </>
  );
}
