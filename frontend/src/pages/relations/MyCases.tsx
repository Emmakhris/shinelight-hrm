import { Alert, Button, Card, CardContent, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { api, openBlob } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MyCases() {
  const q = useApi<R>("/relations/my/");
  const [raise, setRaise] = useState(false);
  const [respond, setRespond] = useState<R | null>(null);
  const [appeal, setAppeal] = useState<R | null>(null);
  const [withdraw, setWithdraw] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const d = q.data || {};
  return (
    <>
      <PageHeader title="Raise a concern" subtitle="Grievances, harassment and whistleblowing reports are handled confidentially by HR."
        actions={<Button variant="contained" onClick={() => setRaise(true)}>Raise a concern</Button>} />
      <Alert severity="info" sx={{ mb: 2 }}>Only the assigned HR case officer and investigators see your report. Your supervisor is not told unless it becomes necessary. Harassment and whistleblowing reports can be made anonymously. Retaliation against anyone who raises a concern in good faith is itself misconduct.</Alert>
      <Section title="Matters you raised" dense>
        <DataTable dense rows={d.raised || []} emptyTitle="You have not raised any concerns" columns={[
          { key: "reference", label: "Ref" }, { key: "type", label: "Type" }, { key: "title", label: "Subject" },
          { key: "created_at", label: "Raised", render: (r) => fmtDate(r.created_at) },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "closed" ? "completed" : r.status === "withdrawn" ? "cancelled" : "in_progress"} label={r.status_label} /> },
          { key: "_a", label: "", render: (r) => r.can_withdraw && <Button size="small" onClick={() => setWithdraw(r)}>Withdraw</Button> },
        ]} />
      </Section>
      {(d.actions || []).map((a: R) => (
        <Card key={a.id} sx={{ mb: 2 }}><CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography variant="h6">{a.action_label}</Typography>
            {a.letter && <Button onClick={() => openBlob(`/relations/my/letter/${a.id}/`)}>Read letter</Button>}</Stack>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", my: 1 }}>{a.details}</Typography>
          <Stack spacing={0.5}>
            <Field label="Effective" value={`${fmtDate(a.effective_date)}${a.expires_on ? ` · on record until ${fmtDate(a.expires_on)}` : ""}`} />
            {a.employee_response && <Field label="Your response" value={a.employee_response} />}
            {a.appeals.map((ap: R) => <Field key={ap.id} label={`Appeal (${ap.status})`} value={`${ap.grounds}${ap.decision ? ` — Decision: ${ap.decision}` : ""}`} />)}
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Button onClick={() => setRespond(a)}>{a.acknowledged_at ? "Update response" : "Acknowledge / respond"}</Button>
            {a.can_appeal && <Button variant="contained" onClick={() => setAppeal(a)}>Appeal (by {fmtDate(a.appeal_deadline)})</Button>}
          </Stack>
        </CardContent></Card>
      ))}
      <FormDialog open={raise} title="Raise a concern" onClose={() => setRaise(false)} initial={{ case_type: "grievance", severity: "medium", is_anonymous: false, respondents: [] }}
        fields={[{ name: "case_type", label: "Type", type: "select", required: true, options: d.types || [] },
          { name: "title", label: "Subject", width: 8 }, { name: "incident_date", label: "When did it happen?", type: "date", width: 4 },
          { name: "description", label: "What happened? Include dates, places and any witnesses.", type: "textarea", required: true },
          { name: "respondents", label: "People involved (optional)", type: "multiref", ref: "/directory/" },
          { name: "severity", label: "How serious is it?", type: "select", width: 6, options: [["low", "Low"], ["medium", "Medium"], ["high", "High"], ["critical", "Critical (safety risk)"]].map(([value, label]) => ({ value, label })) },
          { name: "is_anonymous", label: "Report anonymously (harassment / whistleblowing only)", type: "checkbox", width: 6, hidden: (v) => !["harassment", "whistleblowing"].includes(String(v.case_type)) }]}
        onSubmit={async (v) => { const r = await api.post<R>("/relations/cases/", { ...(v as R), own: true }); toast.ok(`${r.data.detail} Reference ${r.data.reference}.`); inv("/relations/"); }} />
      <FormDialog open={!!respond} title="Your response" onClose={() => setRespond(null)} initial={{ response: respond?.employee_response || "" }}
        intro={<Alert severity="info">Acknowledging confirms you received the outcome; it does not mean you agree with it.</Alert>}
        fields={[{ name: "response", label: "Your written response (optional)", type: "textarea" }]}
        onSubmit={async (v) => { await post("/relations/my/", { action: respond?.id, ...(v as R) }); toast.ok("Saved."); inv("/relations/"); }} />
      <FormDialog open={!!appeal} title="Lodge an appeal" onClose={() => setAppeal(null)}
        intro={<Alert severity="info">Your appeal is heard by a senior manager who was not involved in the original decision.</Alert>}
        fields={[{ name: "grounds", label: "Grounds of appeal", type: "textarea", required: true }]}
        onSubmit={async (v) => { await post("/relations/my/", { action: appeal?.id, appeal: true, ...(v as R) }); toast.ok("Appeal lodged."); inv("/relations/"); }} />
      <ConfirmDialog open={!!withdraw} title="Withdraw this matter?" comment="optional" confirmLabel="Withdraw" onClose={() => setWithdraw(null)}
        onConfirm={async (reason) => { await post(`/relations/my/${withdraw?.id}/withdraw/`, { reason }); toast.ok("Withdrawn."); inv("/relations/"); }} />
    </>
  );
}
