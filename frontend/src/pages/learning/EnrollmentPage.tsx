import CheckCircle from "@mui/icons-material/CheckCircle";
import RadioButtonUnchecked from "@mui/icons-material/RadioButtonUnchecked";
import { Alert, Box, Button, Checkbox, FormControlLabel, Grid2 as Grid, Link, List, ListItemButton, ListItemIcon,
  ListItemText, Radio, RadioGroup, Rating, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { errorMessage } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtDateTime } from "../../utils";
import { ENROLL_STATUS_CHIP } from "./MyLearning";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function EnrollmentPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const q = useApi<R>(`/learning/enrollments/${id}/`);
  const [active, setActive] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<string, number[]>>({});
  const [result, setResult] = useState<R | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | "feedback" | "effect" | "complete" | "cancel">(null);
  if (q.isLoading) return <Loading />;
  const e = q.data;
  if (!e) return <ErrorAlert error={q.error} />;
  const refresh = () => inv("/learning/");
  const learning = e.is_mine && ["enrolled", "in_progress"].includes(e.status);
  const modules: R[] = e.modules || [];
  const allDone = modules.every((m) => m.done);
  const mod = modules.find((m) => m.id === active) || modules.find((m) => !m.done) || modules[0];
  const markDone = async (m: R) => {
    try { await post(`/learning/enrollments/${id}/module/`, { module: m.id }); refresh(); } catch (x) { toast.error(x); }
  };
  const submitQuiz = async () => {
    setErr(null);
    try { const r = await post<R>(`/learning/enrollments/${id}/quiz/`, { answers }); setResult(r); refresh(); } catch (x) { setErr(errorMessage(x)); }
  };
  return (
    <>
      <PageHeader title={e.course_title} subtitle={`${e.employee_name}${e.session_start ? ` · ${fmtDateTime(e.session_start)} · ${e.session_venue || ""}` : ""}${e.due_date ? ` · due ${fmtDate(e.due_date)}` : ""}`}
        crumbs={[{ label: e.is_mine ? "My learning" : "Training", to: e.is_mine ? "/learning" : e.is_supervisor ? "/learning/team" : "/learning/admin" }, { label: e.course_title }]}
        actions={<>
          <StatusChip value={ENROLL_STATUS_CHIP(e.status)} label={e.status_label} />
          {e.is_mine && e.status === "completed" && !e.feedback_rating && <Button variant="contained" onClick={() => setDialog("feedback")}>Rate this training</Button>}
          {(e.is_supervisor || can("learning.manage")) && !e.is_mine && e.status === "completed" && !e.effectiveness_rating && <Button variant="contained" onClick={() => setDialog("effect")}>Evaluate impact</Button>}
          {can("learning.manage") && ["enrolled", "in_progress"].includes(e.status) && <Button onClick={() => setDialog("complete")}>Record completion</Button>}
          {["pending", "enrolled", "waitlisted", "returned"].includes(e.status) && (e.is_mine && e.source !== "mandatory" || can("learning.manage")) && <Button color="error" onClick={() => setDialog("cancel")}>Cancel</Button>}
        </>} />
      {e.status === "pending" && <Alert severity="info" sx={{ mb: 2 }}>Waiting for approval. Track it under My requests.</Alert>}
      {e.status === "waitlisted" && <Alert severity="info" sx={{ mb: 2 }}>The session is full; you are on the waitlist and will be enrolled if a seat frees up.</Alert>}
      {e.status === "completed" && <Alert severity="success" sx={{ mb: 2 }}>Completed {fmtDate(e.completed_at)}{e.quiz_score != null && ` with ${e.quiz_score}%`}{e.expires_on && `; valid until ${fmtDate(e.expires_on)}`}{Number(e.cpd_credits) > 0 && `. ${Number(e.cpd_credits)} CPD credits recorded`}.</Alert>}
      {e.status === "failed" && <Alert severity="error" sx={{ mb: 2 }}>Not passed{e.quiz_score != null && ` (${e.quiz_score}%, pass mark ${e.pass_mark}%)`}. Speak to the training office about retaking.</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: modules.length ? 4 : 12 }}>
          <Section title="About this course">
            <Stack spacing={1}>
              {e.course_description && <Typography variant="body2">{e.course_description}</Typography>}
              {e.course_objectives && <Field label="You will be able to" value={e.course_objectives} />}
              {e.reason && <Field label="Reason for request" value={e.reason} />}
              {e.feedback_rating && <Field label="Participant rating" value={<Rating readOnly value={e.feedback_rating} size="small" />} />}
              {e.effectiveness_rating && <Field label="Applied on the job (supervisor)" value={<><Rating readOnly value={e.effectiveness_rating} size="small" /> {e.effectiveness_comments}</>} />}
            </Stack>
          </Section>
          {modules.length > 0 && <Section title="Modules" dense>
            <List dense>
              {modules.map((m) => (
                <ListItemButton key={m.id} selected={mod?.id === m.id} onClick={() => setActive(m.id)}>
                  <ListItemIcon sx={{ minWidth: 32 }}>{m.done ? <CheckCircle color="success" fontSize="small" /> : <RadioButtonUnchecked fontSize="small" />}</ListItemIcon>
                  <ListItemText primary={m.title} secondary={`${m.minutes} min`} />
                </ListItemButton>
              ))}
              {e.questions?.length > 0 && <ListItemButton selected={active === -1} onClick={() => setActive(-1)} disabled={!allDone}>
                <ListItemIcon sx={{ minWidth: 32 }}>{e.status === "completed" ? <CheckCircle color="success" fontSize="small" /> : <RadioButtonUnchecked fontSize="small" />}</ListItemIcon>
                <ListItemText primary="Assessment" secondary={`Pass mark ${e.pass_mark}%`} />
              </ListItemButton>}
            </List>
          </Section>}
        </Grid>
        {modules.length > 0 && <Grid size={{ xs: 12, md: 8 }}>
          {active === -1 && e.questions?.length ? (
            <Section title="Assessment">
              {result && <Alert severity={result.passed ? "success" : "warning"} sx={{ mb: 2 }}>You scored {result.score}%. {result.passed ? "Well done — the course is complete." : result.status === "failed" ? "No attempts left." : `Pass mark is ${e.pass_mark}%. Review the modules and try again (attempt ${result.attempts} of 3).`}</Alert>}
              {learning ? <Stack spacing={2}>
                {e.questions.map((qn: R, i: number) => (
                  <Box key={qn.id}>
                    <Typography fontWeight={600}>{i + 1}. {qn.text}</Typography>
                    {qn.multiple ? qn.options.map((o: string, j: number) => (
                      <FormControlLabel key={j} control={<Checkbox checked={(answers[qn.id] || []).includes(j)}
                        onChange={(ev) => setAnswers({ ...answers, [qn.id]: ev.target.checked ? [...(answers[qn.id] || []), j] : (answers[qn.id] || []).filter((x) => x !== j) })} />} label={o} />
                    )) : <RadioGroup value={answers[qn.id]?.[0] ?? ""} onChange={(ev) => setAnswers({ ...answers, [qn.id]: [Number(ev.target.value)] })}>
                      {qn.options.map((o: string, j: number) => <FormControlLabel key={j} value={j} control={<Radio />} label={o} />)}
                    </RadioGroup>}
                  </Box>
                ))}
                {err && <Alert severity="error">{err}</Alert>}
                <Button variant="contained" onClick={submitQuiz} disabled={Object.keys(answers).length < e.questions.length}>Submit answers</Button>
              </Stack> : <Typography color="text.secondary">The assessment is closed.</Typography>}
            </Section>
          ) : mod && (
            <Section title={mod.title}>
              {mod.content && <Typography sx={{ whiteSpace: "pre-wrap", mb: 2 }}>{mod.content}</Typography>}
              {mod.url && <Link href={mod.url} target="_blank" rel="noopener">{mod.kind === "video" ? "Watch the video" : "Open the resource"} ↗</Link>}
              {learning && <Box sx={{ mt: 2 }}>{mod.done ? <Typography color="success.main">Module completed.</Typography>
                : <Button variant="contained" onClick={() => markDone(mod)}>Mark as complete</Button>}</Box>}
              {learning && allDone && e.questions?.length > 0 && <Button sx={{ mt: 2 }} onClick={() => setActive(-1)}>Go to the assessment →</Button>}
            </Section>
          )}
        </Grid>}
      </Grid>
      <FormDialog open={dialog === "feedback"} title="How was the training?" onClose={() => setDialog(null)} initial={{ rating: 5 }}
        fields={[{ name: "rating", label: "Overall (1–5)", type: "select", required: true, options: [5, 4, 3, 2, 1].map((v) => ({ value: v, label: String(v) })) },
          { name: "comments", label: "What was useful? What could improve?", type: "textarea" }]}
        onSubmit={async (d) => { await post(`/learning/enrollments/${id}/feedback/`, d); toast.ok("Thank you for your feedback."); refresh(); }} />
      <FormDialog open={dialog === "effect"} title="Is the training being applied?" onClose={() => setDialog(null)} initial={{ rating: 4 }}
        intro={<Alert severity="info">Rate how {e.employee_name} is applying what they learnt, some weeks after the course.</Alert>}
        fields={[{ name: "rating", label: "Impact on the job (1–5)", type: "select", required: true, options: [5, 4, 3, 2, 1].map((v) => ({ value: v, label: String(v) })) },
          { name: "comments", label: "Examples", type: "textarea" }]}
        onSubmit={async (d) => { await post(`/learning/enrollments/${id}/effectiveness/`, d); toast.ok("Evaluation saved."); refresh(); }} />
      <FormDialog open={dialog === "complete"} title="Record completion" onClose={() => setDialog(null)} initial={{ completed_on: new Date().toISOString().slice(0, 10) }}
        intro={<Alert severity="info">For external or on-the-job training. CPD credits and any linked clinical competency are recorded automatically.</Alert>}
        fields={[{ name: "completed_on", label: "Completed on", type: "date", required: true, width: 6 }, { name: "score", label: "Score % (optional)", type: "number", width: 6 },
          { name: "assessor", label: "Assessor / provider" }]}
        onSubmit={async (d) => { await post(`/learning/enrollments/${id}/complete/`, d); toast.ok("Completion recorded."); refresh(); }} />
      <ConfirmDialog open={dialog === "cancel"} title="Cancel this enrolment?" color="error" comment="optional" confirmLabel="Cancel enrolment" onClose={() => setDialog(null)}
        onConfirm={async (reason) => { await post(`/learning/enrollments/${id}/cancel/`, { reason }); toast.ok("Cancelled."); refresh(); }} />
    </>
  );
}
