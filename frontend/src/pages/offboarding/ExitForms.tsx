import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Rating, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { errorMessage } from "../../api/client";
import { post, useInvalidate } from "../../api/hooks";
import { useToast } from "../../components/Feedback";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const opts = (p: string[][]) => p.map(([value, label]) => ({ value, label }));

export const EXIT_TYPES = opts([["resignation", "Resignation"], ["retirement", "Retirement"], ["contract_end", "End of contract"], ["termination", "Termination (notice)"],
  ["dismissal", "Dismissal"], ["redundancy", "Redundancy"], ["mutual", "Mutual separation"], ["death", "Death in service"], ["probation_termination", "Termination during probation"]]);
export const REASONS = opts([["better_pay", "Better pay / benefits"], ["career", "Career growth"], ["relocation", "Relocation"], ["family", "Family / personal"], ["health", "Health"],
  ["management", "Relationship with management"], ["workload", "Workload / working hours"], ["studies", "Further studies"], ["travel", "Travelling abroad"],
  ["retirement", "Retirement"], ["conduct", "Conduct / performance"], ["other", "Other"]]);

export function ExitInterviewForm({ sep, onDone }: { sep: R; onDone?: () => void }) {
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [f, setF] = useState<R>({ primary_reason: sep.reason || "", what_went_well: "", what_to_improve: "", would_recommend: null, would_return: null });
  const [err, setErr] = useState<string | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const submit = async () => {
    setErr(null);
    try { await post(`/offboarding/separations/${sep.id}/interview/`, { ...f, ratings }); toast.ok("Thank you for your feedback."); inv("/offboarding/"); onDone?.(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Stack spacing={1.5}>
      <Typography variant="body2" color="text.secondary">Your honest feedback helps us improve. Answers are seen only by HR and reported in aggregate.</Typography>
      {(sep.questions || []).map((qn: string) => (
        <Stack key={qn} direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="body2">{qn}</Typography>
          <Rating value={ratings[qn] || 0} onChange={(_, v) => setRatings({ ...ratings, [qn]: v || 0 })} />
        </Stack>))}
      <TextField select label="Main reason for leaving" value={f.primary_reason} onChange={(e) => setF({ ...f, primary_reason: e.target.value })}>
        {REASONS.map((r) => <MenuItem key={r.value} value={r.value}>{r.label}</MenuItem>)}
      </TextField>
      <TextField label="What did we do well?" multiline minRows={2} value={f.what_went_well} onChange={(e) => setF({ ...f, what_went_well: e.target.value })} />
      <TextField label="What should we improve?" multiline minRows={2} value={f.what_to_improve} onChange={(e) => setF({ ...f, what_to_improve: e.target.value })} />
      <Box>
        <FormControlLabel control={<Checkbox checked={f.would_recommend === true} onChange={(e) => setF({ ...f, would_recommend: e.target.checked })} />} label="I would recommend this organization as a place to work" />
        <FormControlLabel control={<Checkbox checked={f.would_return === true} onChange={(e) => setF({ ...f, would_return: e.target.checked })} />} label="I would consider returning in future" />
      </Box>
      {err && <Alert severity="error">{err}</Alert>}
      <Button variant="contained" onClick={submit}>Submit exit interview</Button>
    </Stack>
  );
}
