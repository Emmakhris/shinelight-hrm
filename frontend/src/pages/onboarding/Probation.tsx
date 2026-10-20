import { Alert, Box, Button, Card, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Rating, Stack, Tab, Tabs,
  TextField, Typography } from "@mui/material";
import { useState } from "react";
import { errorMessage } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { Field, PageHeader } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const RECS: Record<string, string> = { confirm: "Confirm appointment", extend: "Extend probation", terminate: "Terminate appointment",
  continue: "Continue probation" };

function ReviewDialog({ review, onClose }: { review: R; onClose: () => void }) {
  const [ratings, setRatings] = useState<Record<string, number>>(review.ratings || {});
  const [f, setF] = useState<R>({ recommendation: "", extend_months: 3, strengths: review.strengths || "", improvements: review.improvements || "",
    reviewer_comments: review.reviewer_comments || "" });
  const [err, setErr] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const inv = useInvalidate();
  const toast = useToast();
  const options = review.review_type === "midpoint" ? ["continue", "terminate"] : ["confirm", "extend", "terminate"];
  const readOnly = !review.can_review;
  const submit = async () => {
    setErr(null);
    try {
      await post(`/onboarding/probation/${review.id}/submit/`, { ...f, ratings });
      toast.ok(f.recommendation === "continue" ? "Review recorded." : "Submitted to HR for decision."); inv("/onboarding/"); onClose();
    } catch (e) { setErr(errorMessage(e)); }
  };
  const ack = async () => {
    try { await post(`/onboarding/probation/${review.id}/acknowledge/`, { comments: comment }); toast.ok("Acknowledged."); inv("/onboarding/"); onClose(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{review.review_type === "midpoint" ? "Mid-probation review" : "End-of-probation review"} — {review.employee_name}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">{review.job_title} · joined {fmtDate(review.hire_date)} · probation ends {fmtDate(review.probation_end_date)}</Typography>
          {(review.criteria || []).map((c: string) => (
            <Stack key={c} direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="body2">{c}</Typography>
              <Rating readOnly={readOnly} value={ratings[c] || 0} onChange={(_, v) => setRatings({ ...ratings, [c]: v || 0 })} />
            </Stack>
          ))}
          {readOnly ? <>
            {review.overall_rating && <Field label="Overall rating" value={`${review.overall_rating} / 5`} />}
            {review.recommendation && <Field label="Recommendation" value={`${RECS[review.recommendation]}${review.extend_months ? ` by ${review.extend_months} month(s)` : ""}`} />}
            {review.strengths && <Field label="Strengths" value={review.strengths} />}
            {review.improvements && <Field label="Areas to improve" value={review.improvements} />}
            {review.reviewer_comments && <Field label="Comments" value={review.reviewer_comments} />}
            {review.employee_comments && <Field label="Employee's comments" value={review.employee_comments} />}
          </> : <>
            <TextField select label="Recommendation" value={f.recommendation} onChange={(e) => setF({ ...f, recommendation: e.target.value })} required>
              {options.map((o) => <MenuItem key={o} value={o}>{RECS[o]}</MenuItem>)}
            </TextField>
            {f.recommendation === "extend" && <TextField type="number" label="Extend by (months, max 6)" value={f.extend_months} onChange={(e) => setF({ ...f, extend_months: e.target.value })} />}
            <TextField label="Strengths" multiline minRows={2} value={f.strengths} onChange={(e) => setF({ ...f, strengths: e.target.value })} />
            <TextField label={["extend", "terminate"].includes(f.recommendation) ? "Performance gaps (required)" : "Areas to improve"} multiline minRows={2}
              value={f.improvements} onChange={(e) => setF({ ...f, improvements: e.target.value })} />
            <TextField label="Comments" multiline minRows={2} value={f.reviewer_comments} onChange={(e) => setF({ ...f, reviewer_comments: e.target.value })} />
            {f.recommendation && f.recommendation !== "continue" && <Alert severity="info">HR reviews the recommendation{f.recommendation !== "confirm" ? " and the HR Director decides" : ""}. Confirmation is effective from the end of probation.</Alert>}
          </>}
          {review.is_self && !review.employee_acknowledged_at && ["submitted", "completed"].includes(review.status) &&
            <TextField label="Your comments (optional)" multiline minRows={2} value={comment} onChange={(e) => setComment(e.target.value)} />}
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        {review.can_review && <Button variant="contained" onClick={submit}>Submit review</Button>}
        {review.is_self && !review.employee_acknowledged_at && ["submitted", "completed"].includes(review.status) && <Button variant="contained" onClick={ack}>Acknowledge</Button>}
      </DialogActions>
    </Dialog>
  );
}

export default function Probation() {
  const { can } = useAuth();
  const [tab, setTab] = useState(can("onboarding.view") ? "all" : "mine");
  const [status, setStatus] = useState("scheduled");
  const q = useApi<R>("/onboarding/probation/", { mine: tab === "mine" ? 1 : undefined, status: status || undefined, page_size: 200 });
  const [open, setOpen] = useState<R | null>(null);
  return (
    <>
      <PageHeader title="Probation reviews" subtitle="Mid-point and end-of-probation reviews are scheduled automatically from the hire and probation end dates." />
      <Card sx={{ mb: 2 }}>
        <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} sx={{ pr: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ flex: 1 }}>
            <Tab value="mine" label="Assigned to me" />{can("onboarding.view") && <Tab value="all" label="All reviews" />}
          </Tabs>
          <TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 180, m: 1 }}>
            <MenuItem value="">All</MenuItem>
            {[["scheduled", "Scheduled"], ["submitted", "Awaiting decision"], ["returned", "Returned"], ["completed", "Completed"], ["rejected", "Not approved"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
          </TextField>
        </Stack>
      </Card>
      <Card>
        <DataTable loading={q.isLoading} rows={q.data?.results || []} onRowClick={setOpen} emptyTitle="No probation reviews" columns={[
          { key: "due_date", label: "Due", render: (r) => <Box sx={{ color: r.status === "scheduled" && r.due_date < new Date().toISOString().slice(0, 10) ? "error.main" : undefined }}>{fmtDate(r.due_date)}</Box> },
          { key: "employee_name", label: "Employee", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.job_title} · {r.department_name}</small></> },
          { key: "review_type", label: "Review", render: (r) => (r.review_type === "midpoint" ? "Mid-point" : "Final") },
          { key: "probation_end_date", label: "Probation ends", hideOnMobile: true, render: (r) => fmtDate(r.probation_end_date) },
          { key: "reviewer_name", label: "Reviewer", hideOnMobile: true, render: (r) => r.reviewer_name || "Supervisor" },
          { key: "recommendation", label: "Recommendation", render: (r) => (r.recommendation ? RECS[r.recommendation] : "—") },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> },
          { key: "_a", label: "", align: "right", render: (r) => r.can_review ? <Button size="small" variant="contained">Review</Button> : <Button size="small">View</Button> },
        ]} />
      </Card>
      {open && <ReviewDialog review={open} onClose={() => setOpen(null)} />}
    </>
  );
}
