import { Alert, Button, Card, CardContent, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { ExitInterviewForm, REASONS } from "./ExitForms";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MyExit() {
  const list = useApi<R>("/offboarding/separations/", { mine: 1 });
  const current = (list.data?.results || []).find((s: R) => !["withdrawn", "rejected"].includes(s.status));
  const detail = useApi<R>(current ? `/offboarding/separations/${current.id}/` : null);
  const assets = useApi<R>("/assets/assignments/", { mine: 1, open: 1 });
  const [resigning, setResigning] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  const s = detail.data;
  const toReturn = (assets.data?.results || []).filter((a: R) => a.returnable);
  return (
    <>
      <PageHeader title="Resignation & exit" subtitle="Submit a resignation, follow your clearance and complete the exit interview."
        actions={!current && <Button variant="contained" color="error" onClick={() => setResigning(true)}>Submit resignation</Button>} />
      {!current && <Card><CardContent><Typography>You have no exit in progress. If you decide to resign, please speak to your supervisor first. Your notice period depends on your length of service (normally one month after three years' service, two weeks before that).</Typography></CardContent></Card>}
      {s && <>
        <Section title={`Your exit (${s.reference})`} actions={<StatusChip value={s.status === "clearance" ? "in_progress" : s.status} label={s.status_label} />}>
          <Stack spacing={1}>
            <Field label="Last working day" value={fmtDate(s.last_working_day)} />
            <Field label="Notice" value={`${s.notice_required_days} days required${s.notice_shortfall_days ? `; ${s.notice_shortfall_days} day(s) short` : ""}`} />
            {s.progress.total > 0 && <Field label="Clearance" value={`${s.progress.done} of ${s.progress.total} items cleared`} />}
          </Stack>
        </Section>
        {toReturn.length > 0 && <Alert severity="warning" sx={{ mb: 2 }}>Please return before your last day: {toReturn.map((a: R) => `${a.item}${a.tag ? ` (${a.tag})` : ""}`).join(", ")}.</Alert>}
        {s.status === "clearance" && s.exit_interview && !s.exit_interview.completed_at && <Section title="Exit interview"><ExitInterviewForm sep={s} /></Section>}
        {s.exit_interview?.completed_at && <Alert severity="success">Thank you for completing the exit interview.</Alert>}
      </>}
      <FormDialog open={resigning} title="Submit resignation" onClose={() => setResigning(false)} initial={{ exit_type: "resignation", notice_date: new Date().toISOString().slice(0, 10) }}
        intro={<Alert severity="info">Your supervisor and HR will acknowledge it. You can withdraw it until it has been accepted.</Alert>}
        fields={[{ name: "last_working_day", label: "Proposed last working day", type: "date", required: true },
          { name: "reason", label: "Main reason (optional)", type: "select", options: REASONS },
          { name: "details", label: "Resignation letter", type: "textarea", required: true }]}
        onSubmit={async (v) => { await api.post("/offboarding/separations/", { ...(v as R), exit_type: "resignation" }); toast.ok("Resignation submitted."); inv("/offboarding/"); }} />
    </>
  );
}
