import Lock from "@mui/icons-material/Lock";
import { Alert, Box, Button, Card, CardContent, Chip, FormControlLabel, Grid2 as Grid, MenuItem, Rating, Stack, Switch, TextField,
  Typography } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { download } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { fmtDateTime, titleCase } from "../../utils";

type T = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function TicketDetail() {
  const { id } = useParams();
  const { me, can } = useAuth();
  const agent = can("servicedesk.agent") || can("servicedesk.manage");
  const { data: t, isLoading, error } = useApi<T>(`/helpdesk/tickets/${id}/`);
  const agents = useApi<{ id: number; name: string }[]>(agent ? "/helpdesk/tickets/agents/" : null);
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  const [dialog, setDialog] = useState<null | "resolve" | "pending" | "reopen" | "cancel">(null);
  const [rating, setRating] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const inv = useInvalidate();
  const toast = useToast();
  if (isLoading) return <Loading />;
  if (error || !t) return <ErrorAlert error={error} />;
  const isRequester = t.requester === me?.id;
  const open = ["new", "open", "pending_employee"].includes(t.status);
  const run = async (path: string, data?: unknown, msg?: string) => {
    setErr(null);
    try { await post(`/helpdesk/tickets/${id}/${path}/`, data); if (msg) toast.ok(msg); inv("/helpdesk/"); }
    catch (e) { setErr(e); throw e; }
  };
  return (
    <>
      <PageHeader title={`${t.reference} — ${t.subject}`} crumbs={[{ label: "Help desk", to: agent ? "/helpdesk/queue" : "/helpdesk" }, { label: t.reference }]}
        actions={<Stack direction="row" spacing={1} alignItems="center">
          <StatusChip value={t.status} label={titleCase(t.status === "pending_employee" ? "waiting on employee" : t.status)} />
          {t.is_overdue && <Chip color="error" label="Overdue" />}
          {t.is_confidential && <Chip icon={<Lock />} label="Confidential" />}
        </Stack>} />
      <ErrorAlert error={err} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 8 }}>
          <Card sx={{ mb: 2 }}><CardContent>
            <Typography variant="caption" color="text.secondary">{t.requester_name} · {fmtDateTime(t.created_at)} · via {t.channel}</Typography>
            <Typography sx={{ whiteSpace: "pre-wrap", mt: 1 }}>{t.description}</Typography>
            {Object.keys(t.form_data || {}).length > 0 && (
              <Grid container spacing={2} sx={{ mt: 1 }}>
                {Object.entries(t.form_data).map(([k, v]) => <Grid key={k} size={6}><Field label={titleCase(k)} value={String(v)} /></Grid>)}
              </Grid>
            )}
          </CardContent></Card>
          {t.comments.map((c: T) => (
            <Card key={c.id} sx={{ mb: 1.5, ml: c.is_staff_reply ? 0 : 4, bgcolor: c.is_internal ? "#fff8e1" : c.is_staff_reply ? "#f1f7fb" : undefined }}>
              <CardContent sx={{ py: 1.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {c.author_name} · {fmtDateTime(c.created_at)} {c.is_internal && <b>· INTERNAL NOTE</b>}
                </Typography>
                <Typography sx={{ whiteSpace: "pre-wrap" }}>{c.body}</Typography>
                {c.attachment && <Button size="small" onClick={() => download(`/documents/${c.attachment}/download/`)}>Download attachment</Button>}
              </CardContent>
            </Card>
          ))}
          {t.resolution && <Alert severity="success" sx={{ mb: 2 }}><b>Resolution:</b> {t.resolution}</Alert>}
          {open && (
            <Card><CardContent>
              <TextField fullWidth multiline minRows={3} placeholder={agent && !isRequester ? "Reply to the employee…" : "Add more information…"}
                value={body} onChange={(e) => setBody(e.target.value)} />
              <Stack direction="row" spacing={1} sx={{ mt: 1 }} alignItems="center">
                {agent && !isRequester && <FormControlLabel control={<Switch checked={internal} onChange={(e) => setInternal(e.target.checked)} />} label="Internal note" />}
                <Box flex={1} />
                <Button variant="contained" disabled={!body.trim()} onClick={async () => { await run("comment", { body, internal }); setBody(""); }}>
                  {internal ? "Add note" : "Send"}
                </Button>
              </Stack>
            </CardContent></Card>
          )}
          {isRequester && t.status === "resolved" && (
            <Section title="How did we do?">
              <Rating value={rating} onChange={(_, v) => setRating(v)} size="large" />
              <TextField fullWidth label="Comments (optional)" value={feedback} onChange={(e) => setFeedback(e.target.value)} sx={{ my: 1 }} />
              <Stack direction="row" spacing={1}>
                <Button variant="contained" disabled={!rating} onClick={() => run("rate", { rating, feedback }, "Thank you for your feedback.")}>Submit rating</Button>
                <Button color="warning" onClick={() => setDialog("reopen")}>Not resolved — reopen</Button>
              </Stack>
            </Section>
          )}
          {t.rating && <Alert severity="info" sx={{ mt: 2 }}>Rated {t.rating}/5 {t.feedback && `— “${t.feedback}”`}</Alert>}
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Details">
            <Stack spacing={1.5}>
              <Field label="Service" value={`${t.category_name} › ${t.service_name}`} />
              <Field label="Priority" value={titleCase(t.priority)} />
              <Field label="Assigned to" value={t.assignee_name || "Unassigned"} />
              <Field label="First response due" value={t.first_response_at ? `Responded ${fmtDateTime(t.first_response_at)}` : fmtDateTime(t.response_due)} />
              <Field label="Resolution due" value={fmtDateTime(t.resolution_due)} />
              {t.resolved_at && <Field label="Resolved" value={`${fmtDateTime(t.resolved_at)}${t.resolution_breached ? " (outside SLA)" : " (within SLA)"}`} />}
              {t.employee_name && <Field label="Employee" value={t.employee_name} />}
            </Stack>
          </Section>
          {agent && open && (
            <Section title="Actions">
              <Stack spacing={1}>
                <TextField select label="Assign to" value={t.assignee || ""} onChange={(e) => run("assign", { user: e.target.value }, "Reassigned.")}>
                  {(agents.data || []).map((a) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
                </TextField>
                {t.assignee !== me?.id && <Button onClick={() => run("assign", { user: me?.id }, "Assigned to you.")}>Take ownership</Button>}
                {t.status !== "pending_employee" ? <Button onClick={() => setDialog("pending")}>Ask employee for information</Button>
                  : <Button onClick={() => run("status", { status: "open" }, "Resumed.")}>Resume</Button>}
                {t.letter_template && <Button onClick={() => run("generate-letter", undefined, "Letter generated and sent to the employee.")}>Generate letter</Button>}
                <Button variant="contained" color="success" onClick={() => setDialog("resolve")}>Resolve</Button>
              </Stack>
            </Section>
          )}
          {isRequester && open && <Button color="error" onClick={() => setDialog("cancel")}>Withdraw request</Button>}
          <Section title="History">
            {t.events.map((e: T) => (
              <Typography key={e.id} variant="caption" display="block" color="text.secondary">
                {fmtDateTime(e.created_at)} · {e.actor_name}: {titleCase(e.event.replace(":", " "))} {e.detail}
              </Typography>
            ))}
          </Section>
        </Grid>
      </Grid>
      <ConfirmDialog open={dialog === "resolve"} onClose={() => setDialog(null)} title="Resolve request" confirmLabel="Resolve" color="success"
        comment="required" message="Describe what was done. The employee is notified and asked to rate the service."
        onConfirm={(c) => run("resolve", { resolution: c }, "Resolved.")} />
      <ConfirmDialog open={dialog === "pending"} onClose={() => setDialog(null)} title="Ask the employee" confirmLabel="Send" comment="required"
        message="The SLA clock pauses until the employee replies." onConfirm={(c) => run("status", { status: "pending_employee", note: c })} />
      <ConfirmDialog open={dialog === "reopen"} onClose={() => setDialog(null)} title="Reopen request" confirmLabel="Reopen" color="warning" comment="required"
        onConfirm={(c) => run("reopen", { reason: c }, "Reopened.")} />
      <ConfirmDialog open={dialog === "cancel"} onClose={() => setDialog(null)} title="Withdraw request?" confirmLabel="Withdraw" color="error" comment="optional"
        onConfirm={(c) => run("cancel", { reason: c }, "Withdrawn.")} />
    </>
  );
}
