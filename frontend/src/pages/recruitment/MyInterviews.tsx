import { Alert, Box, Button, Card, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem,
  Rating, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { errorMessage, openBlob } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { fmtDateTime } from "../../utils";
import { RECOMMENDATIONS } from "./constants";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function ScoreDialog({ iv, onClose }: { iv: R | null; onClose: () => void }) {
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [rec, setRec] = useState("");
  const [strengths, setStrengths] = useState("");
  const [concerns, setConcerns] = useState("");
  const [coi, setCoi] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  if (!iv) return null;
  const submit = async () => {
    setErr(null);
    try {
      await post(`/recruitment/interviews/${iv.id}/score/`, { ratings, recommendation: rec, strengths, concerns, conflict_of_interest: coi });
      toast.ok("Scorecard submitted."); inv("/recruitment/"); onClose();
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Scorecard — {iv.candidate_name}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{iv.round_name} for {iv.vacancy_title}. Rate each criterion from 1 (poor) to 5 (excellent). You will see colleagues' scores after you submit yours.</Typography>
        <Stack spacing={1.5}>
          {(iv.criteria || []).map((c: R) => (
            <Stack key={c.name} direction="row" justifyContent="space-between" alignItems="center">
              <Box><b>{c.name}</b> <small>({c.weight}%)</small></Box>
              <Rating value={ratings[c.name] || 0} onChange={(_, v) => setRatings((r) => ({ ...r, [c.name]: v || 0 }))} />
            </Stack>
          ))}
          <TextField select label="Recommendation" value={rec} onChange={(e) => setRec(e.target.value)} required>
            {RECOMMENDATIONS.map((r) => <MenuItem key={r.value} value={r.value}>{r.label}</MenuItem>)}
          </TextField>
          <TextField label="Strengths / evidence" value={strengths} onChange={(e) => setStrengths(e.target.value)} multiline minRows={2} />
          <TextField label={["no", "strong_no"].includes(rec) ? "Concerns (required)" : "Concerns"} value={concerns} onChange={(e) => setConcerns(e.target.value)} multiline minRows={2} />
          <FormControlLabel control={<Checkbox checked={coi} onChange={(e) => setCoi(e.target.checked)} />}
            label="I have a conflict of interest with this candidate (my score is excluded from the summary)" />
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={submit}>Submit scorecard</Button></DialogActions>
    </Dialog>
  );
}

export default function MyInterviews() {
  const q = useApi<R>("/recruitment/interviews/", { mine: 1, page_size: 100 });
  const [scoring, setScoring] = useState<R | null>(null);
  return (
    <>
      <PageHeader title="My interview panels" subtitle="Interviews you sit on. Submit a scorecard for each candidate after the interview." />
      <Card>
        <DataTable loading={q.isLoading} rows={q.data?.results || []} emptyTitle="You are not on any interview panel"
          columns={[
            { key: "scheduled_at", label: "When", render: (r) => fmtDateTime(r.scheduled_at) },
            { key: "candidate_name", label: "Candidate", render: (r) => <><b>{r.candidate_name}</b><br /><small>{r.vacancy_title}</small></> },
            { key: "round_name", label: "Round", hideOnMobile: true, render: (r) => <>{r.round_name}<br /><small>{r.venue}</small></> },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> },
            { key: "my", label: "My scorecard", render: (r) => (r.my_scorecard ? `${Number(r.my_scorecard.overall_score)}/100` : "—") },
            { key: "_a", label: "", align: "right", render: (r) => <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button size="small" onClick={() => openBlob(`/recruitment/interviews/${r.id}/cv/`)}>CV</Button>
              {!r.my_scorecard && r.status !== "cancelled" && <Button size="small" variant="contained" onClick={() => setScoring(r)}>Score</Button>}
            </Stack> },
          ]} />
      </Card>
      {scoring && <ScoreDialog iv={scoring} onClose={() => setScoring(null)} />}
    </>
  );
}
