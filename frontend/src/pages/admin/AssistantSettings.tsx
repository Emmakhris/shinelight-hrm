import { Alert, Button, Grid2 as Grid, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { ErrorAlert, Loading, useToast } from "../../components/Feedback";
import { Kpi, PageHeader, Section } from "../../components/PageHeader";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function AssistantSettings() {
  const { data, isLoading, error } = useApi<R>("/assistant/settings/");
  const [form, setForm] = useState<R>({});
  const toast = useToast();
  const inv = useInvalidate();
  useEffect(() => { if (data) setForm(data.settings); }, [data]);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const u = data.usage;
  const save = async () => {
    try {
      await api.patch("/assistant/settings/", { mode: form.mode, daily_limit: form.daily_limit, retention_days: form.retention_days, model: form.model });
      toast.ok("Settings saved."); inv("/assistant/");
    } catch (e) { toast.error(e); }
  };
  return (
    <>
      <PageHeader title="AI assistant" subtitle="A governed HR assistant that answers from approved policies and, if you allow it, the user's own records." />
      {!data.enabled && <Alert severity="info" sx={{ mb: 2 }}>The assistant is switched off. Turn on the "AI HR assistant" feature under Organization settings → Features.</Alert>}
      {!data.configured && <Alert severity="warning" sx={{ mb: 2 }}>No Anthropic API key is set on the server (ANTHROPIC_API_KEY), so the assistant can't answer yet.</Alert>}
      <Section title="Data protection">
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField select fullWidth label="What the assistant may read" value={form.mode || "policies"} onChange={(e) => setForm({ ...form, mode: e.target.value })}
              helperText={form.mode === "hr_data"
                ? "The user's own profile, leave balances, latest payslip and pending requests, plus aggregate reports within their access, are sent to the AI provider when relevant."
                : "Only published knowledge-base articles are sent to the AI provider. No personal data leaves your server."}>
              {Object.entries(data.modes as Record<string, string>).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}><TextField fullWidth type="number" label="Questions per user per day" value={form.daily_limit ?? ""} onChange={(e) => setForm({ ...form, daily_limit: Number(e.target.value) })} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><TextField fullWidth type="number" label="Keep conversations (days)" value={form.retention_days ?? ""} onChange={(e) => setForm({ ...form, retention_days: Number(e.target.value) })} /></Grid>
          <Grid size={{ xs: 12, md: 6 }}><TextField fullWidth label="Model" value={form.model || ""} onChange={(e) => setForm({ ...form, model: e.target.value })} /></Grid>
        </Grid>
        <Stack direction="row" sx={{ mt: 2 }}><Button variant="contained" onClick={save}>Save</Button></Stack>
      </Section>
      <Section title={`Usage (last ${u.days} days)`}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Questions" value={u.questions} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="People using it" value={u.users} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Rated helpful" value={u.rated ? `${Math.round((100 * u.helpful) / u.rated)}%` : "—"} hint={`${u.rated} rated`} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Answers without a source" value={u.unanswered} hint="Gaps in the knowledge base" /></Grid>
        </Grid>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
          Conversations are private to each user. Administrators see counts only, never questions or answers. Tokens used: {u.input_tokens.toLocaleString()} in, {u.output_tokens.toLocaleString()} out.
        </Typography>
      </Section>
      <Section title="How the assistant is governed" dense>
        <Typography variant="body2" component="div">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            <li>It only sees what the signed-in user could already see, through read-only lookups that apply the same permissions as the rest of the system.</li>
            <li>It cannot submit, approve or change anything, and is instructed never to decide or recommend hiring, dismissal, promotion, discipline or pay.</li>
            <li>Policy answers must come from published knowledge-base articles and list their sources; otherwise it says it doesn't know.</li>
            <li>Ghana Card, SSNIT, phone, email and account numbers typed by users are removed before anything is sent.</li>
            <li>Each use is recorded in the audit trail (without content), and conversations are deleted after the retention period.</li>
          </ul>
        </Typography>
      </Section>
    </>
  );
}
