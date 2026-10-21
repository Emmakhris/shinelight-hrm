import ThumbUp from "@mui/icons-material/ThumbUpOutlined";
import { Alert, Box, Button, Card, CardActions, CardContent, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Grid2 as Grid, IconButton, MenuItem, Rating, Slider, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const VALUES = [["teamwork", "Teamwork"], ["patient_care", "Patient / customer care"], ["integrity", "Integrity"], ["innovation", "Innovation"],
  ["extra_mile", "Going the extra mile"], ["leadership", "Leadership"]].map(([value, label]) => ({ value, label }));

function TakeSurvey({ s, onClose }: { s: R; onClose: () => void }) {
  const [answers, setAnswers] = useState<R>({});
  const [err, setErr] = useState<string | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const submit = async () => {
    setErr(null);
    try { await post(`/engagement/surveys/${s.id}/respond/`, { answers }); toast.ok("Thank you for your feedback."); inv("/engagement/"); onClose(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{s.title}</DialogTitle>
      <DialogContent>
        {s.anonymous && <Alert severity="info" sx={{ mb: 2 }}>This survey is anonymous: your answers are not linked to you, and results are only shown for groups of five or more.</Alert>}
        {s.intro && <Typography variant="body2" sx={{ mb: 2 }}>{s.intro}</Typography>}
        <Stack spacing={2.5}>
          {s.questions.map((q: R) => (
            <Box key={q.key}>
              <Typography fontWeight={600} sx={{ mb: 0.5 }}>{q.text}</Typography>
              {q.type === "rating" && <Stack direction="row" spacing={1} alignItems="center"><small>Strongly disagree</small>
                <Rating value={answers[q.key] || 0} onChange={(_, v) => setAnswers({ ...answers, [q.key]: v })} /><small>Strongly agree</small></Stack>}
              {q.type === "enps" && <Box sx={{ px: 1 }}><Slider min={0} max={10} step={1} marks valueLabelDisplay="on" value={answers[q.key] ?? 5}
                onChange={(_, v) => setAnswers({ ...answers, [q.key]: v })} /></Box>}
              {q.type === "choice" && <TextField select fullWidth size="small" value={answers[q.key] || ""} onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })}>
                {(q.options || []).map((o: string) => <MenuItem key={o} value={o}>{o}</MenuItem>)}</TextField>}
              {q.type === "text" && <TextField fullWidth multiline minRows={2} value={answers[q.key] || ""} onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })} />}
            </Box>))}
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Later</Button><Button variant="contained" onClick={submit}>Submit</Button></DialogActions>
    </Dialog>
  );
}

export default function Engagement() {
  const [tab, setTab] = useState(0);
  const surveys = useApi<R[]>("/engagement/surveys/mine/");
  const wall = useApi<R>("/engagement/recognition/", { page_size: 50 });
  const ideas = useApi<R>("/engagement/suggestions/", { page_size: 50 });
  const events = useApi<R[]>("/engagement/events/");
  const [taking, setTaking] = useState<R | null>(null);
  const [dialog, setDialog] = useState<null | "recognise" | "suggest">(null);
  const toast = useToast();
  const inv = useInvalidate();
  const open = (surveys.data || []).filter((s) => !s.responded);
  return (
    <>
      <PageHeader title="Engagement & wellbeing" subtitle="Have your say, recognise colleagues, share ideas and join staff activities."
        actions={<><Button onClick={() => setDialog("suggest")}>Share an idea</Button><Button variant="contained" onClick={() => setDialog("recognise")}>Recognise a colleague</Button></>} />
      {open.map((s) => <Alert key={s.id} severity="info" sx={{ mb: 1 }} action={<Button onClick={() => setTaking(s)}>Take survey</Button>}>
        <b>{s.title}</b>{s.closes_on && ` — closes ${fmtDate(s.closes_on)}`}{s.anonymous && " (anonymous)"}</Alert>)}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Recognition wall" /><Tab label="Suggestion box" /><Tab label="Events & wellness" /></Tabs>
      {tab === 0 && <Grid container spacing={2}>
        {(wall.data?.results || []).map((r: R) => (
          <Grid key={r.id} size={{ xs: 12, md: 6 }}><Card><CardContent>
            <Stack direction="row" justifyContent="space-between"><Chip size="small" color="primary" label={r.value_label} /><small>{fmtDate(r.created_at)}</small></Stack>
            <Typography sx={{ mt: 1 }}><b>{r.giver_name}</b> recognised <b>{r.recipient_name}</b>{r.recipient_department && <small> ({r.recipient_department})</small>}</Typography>
            <Typography variant="body2" sx={{ mt: 0.5 }}>“{r.message}”</Typography>
          </CardContent><CardActions>
            <IconButton size="small" color={r.liked ? "primary" : "default"} onClick={async () => { await post(`/engagement/recognition/${r.id}/like/`); inv("/engagement/"); }} aria-label="Applaud"><ThumbUp fontSize="small" /></IconButton><small>{r.like_count}</small>
          </CardActions></Card></Grid>))}
        {(wall.data?.results || []).length === 0 && <Grid size={12}><Card sx={{ p: 2 }}>No recognition yet — be the first to thank a colleague.</Card></Grid>}
      </Grid>}
      {tab === 1 && <Stack spacing={1.5}>
        {(ideas.data?.results || []).map((s: R) => (
          <Card key={s.id}><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography fontWeight={600}>{s.title}</Typography><StatusChip value={s.status === "implemented" ? "completed" : s.status === "declined" ? "rejected" : "pending"} label={s.status_label} /></Stack>
            <Typography variant="body2" color="text.secondary">{s.category_label} · {s.author_name} · {fmtDate(s.created_at)}</Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>{s.text}</Typography>
            {s.response && <Alert severity="info" sx={{ mt: 1 }}>HR: {s.response}</Alert>}
          </CardContent><CardActions><Button size="small" variant={s.voted ? "contained" : "outlined"} onClick={async () => { await post(`/engagement/suggestions/${s.id}/vote/`); inv("/engagement/"); }}>👍 {s.vote_count}</Button></CardActions></Card>))}
      </Stack>}
      {tab === 2 && <Grid container spacing={2}>
        {(events.data || []).map((e: R) => (
          <Grid key={e.id} size={{ xs: 12, md: 6 }}><Card><CardContent>
            <Typography variant="overline">{e.kind}</Typography><Typography variant="h6">{e.title}</Typography>
            <Typography variant="body2" color="text.secondary">{fmtDateTime(e.starts_at)} · {e.location}{e.capacity ? ` · ${e.attendee_count}/${e.capacity} places` : ""}</Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>{e.description}</Typography>
          </CardContent><CardActions>
            {new Date(e.starts_at) > new Date() && <Button variant={e.attending ? "outlined" : "contained"} onClick={async () => {
              try { const r = await post<R>(`/engagement/events/${e.id}/register/`); toast.ok(r.attending ? "You're registered." : "Registration cancelled."); inv("/engagement/"); } catch (x) { toast.error(x); }
            }}>{e.attending ? "Cancel registration" : "Register"}</Button>}
          </CardActions></Card></Grid>))}
        {(events.data || []).length === 0 && <Grid size={12}><Card sx={{ p: 2 }}>No upcoming events.</Card></Grid>}
      </Grid>}
      {taking && <TakeSurvey s={taking} onClose={() => setTaking(null)} />}
      <FormDialog open={dialog === "recognise"} title="Recognise a colleague" onClose={() => setDialog(null)} initial={{ value: "teamwork", is_public: true }}
        fields={[{ name: "recipient", label: "Colleague", type: "ref", ref: "/directory/", required: true },
          { name: "value", label: "For", type: "select", options: VALUES, required: true },
          { name: "message", label: "What did they do?", type: "textarea", required: true },
          { name: "is_public", label: "Show on the recognition wall", type: "checkbox" }]}
        onSubmit={async (v) => { await api.post("/engagement/recognition/", v); toast.ok("Thank you for recognising your colleague!"); inv("/engagement/"); }} />
      <FormDialog open={dialog === "suggest"} title="Share an idea" onClose={() => setDialog(null)} initial={{ category: "process", anonymous: false }}
        fields={[{ name: "title", label: "Your idea in a few words", required: true },
          { name: "category", label: "Area", type: "select", options: [["process", "Process / efficiency"], ["patient", "Patient / customer experience"], ["welfare", "Staff welfare"], ["safety", "Health & safety"], ["cost", "Cost saving"], ["other", "Other"]].map(([value, label]) => ({ value, label })) },
          { name: "text", label: "Describe it", type: "textarea", required: true },
          { name: "anonymous", label: "Submit anonymously", type: "checkbox" }]}
        onSubmit={async (v) => { await api.post("/engagement/suggestions/", v); toast.ok("Thank you for your idea."); inv("/engagement/"); }} />
    </>
  );
}
