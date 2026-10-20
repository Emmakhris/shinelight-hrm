import { Alert, Box, Button, Card, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { errorMessage } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { RatingSelect } from "./common";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function GiveFeedback({ fr, onClose }: { fr: R; onClose: () => void }) {
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [strengths, setStrengths] = useState("");
  const [improvements, setImprovements] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  const send = async (decline = false) => {
    setErr(null);
    try {
      await post(`/performance/feedback/${fr.id}/submit/`, { ratings, strengths, improvements, decline });
      toast.ok(decline ? "Declined." : "Thank you. Your feedback is combined anonymously with others'."); inv("/performance/"); onClose();
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Feedback for {fr.employee_name}</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2 }}>Your answers are confidential. They are combined with at least two other people's and never shown individually. Rate only what you have observed.</Alert>
        <Stack spacing={1.5}>
          {fr.competencies.map((c: R) => (
            <Stack key={c.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
              <Box flex={1}><b>{c.name}</b><br /><Typography variant="caption">{c.description}</Typography></Box>
              <RatingSelect scale={fr.scale} value={ratings[c.id]} onChange={(v) => setRatings({ ...ratings, [c.id]: v })} label="Rating (optional)" />
            </Stack>
          ))}
          <TextField label="What does this person do well?" multiline minRows={2} value={strengths} onChange={(e) => setStrengths(e.target.value)} />
          <TextField label="What could they do differently?" multiline minRows={2} value={improvements} onChange={(e) => setImprovements(e.target.value)} />
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button color="error" onClick={() => send(true)}>I can't comment</Button><Box flex={1} />
        <Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={() => send(false)}>Submit feedback</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function FeedbackRequests() {
  const q = useApi<R>("/performance/feedback/");
  const [open, setOpen] = useState<R | null>(null);
  return (
    <>
      <PageHeader title="360 feedback requests" subtitle="Colleagues who asked for your confidential feedback." />
      <Card>
        <DataTable loading={q.isLoading} rows={q.data?.results || []} emptyTitle="No feedback requests" columns={[
          { key: "employee_name", label: "Colleague", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.job_title}</small></> },
          { key: "cycle_name", label: "Cycle" }, { key: "relationship_label", label: "Your relationship" },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "submitted" ? "completed" : r.status} label={r.status} /> },
          { key: "submitted_at", label: "Given", render: (r) => fmtDate(r.submitted_at) },
          { key: "_a", label: "", align: "right", render: (r) => r.status === "pending" && <Button size="small" variant="contained" onClick={() => setOpen(r)}>Give feedback</Button> },
        ]} />
      </Card>
      {open && <GiveFeedback fr={open} onClose={() => setOpen(null)} />}
    </>
  );
}
