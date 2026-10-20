import { Alert, AppBar, Box, Button, Card, CardActionArea, CardContent, Checkbox, Chip, Container, FormControlLabel,
  Grid2 as Grid, MenuItem, Stack, TextField, Toolbar, Typography } from "@mui/material";
import { useState, type ReactNode } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { api, errorMessage, fieldErrors } from "../../api/client";
import { useApi } from "../../api/hooks";
import { Empty, ErrorAlert, Loading } from "../../components/Feedback";
import { fmtDate } from "../../utils";
import { VacancyText } from "../me/InternalJobs";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function PublicShell({ org, children }: { org?: string; children: ReactNode }) {
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "#f6f8fb" }}>
      <AppBar position="static" color="inherit" elevation={0} sx={{ borderBottom: "1px solid #e3e8ef" }}>
        <Toolbar><Typography variant="h6" fontWeight={700} color="primary">{org || "Careers"}</Typography></Toolbar>
      </AppBar>
      <Container maxWidth="md" sx={{ py: 3, px: 2 }}>{children}</Container>
      <Typography variant="caption" component="p" color="text.secondary" align="center" sx={{ pb: 3 }}>Powered by ShineLight HRM</Typography>
    </Box>
  );
}

function ApplyForm({ org, vacancy, qualifications }: { org: string; vacancy: R; qualifications: R[] }) {
  const [f, setF] = useState<R>({ first_name: "", last_name: "", email: "", phone: "", gender: "", location: "", highest_qualification: "",
    field_of_study: "", years_experience: "", current_employer: "", current_title: "", linkedin: "", cover_letter: "", website: "",
    consent: false, talent_pool: false });
  const [answers, setAnswers] = useState<R>({});
  const [cv, setCv] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<R | null>(null);
  const [busy, setBusy] = useState(false);
  if (done) return <Alert severity="success">{done.detail} Your reference is <b>{done.reference}</b>.</Alert>;
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setErrors({});
    if (!cv) { setErr("Please attach your CV."); return; }
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => fd.append(k, String(v)));
    fd.append("answers", JSON.stringify(answers));
    fd.append("cv", cv);
    setBusy(true);
    try { setDone((await api.post(`/public/careers/${org}/${vacancy.id}/apply/`, fd)).data); }
    catch (ex) { setErr(errorMessage(ex)); setErrors(fieldErrors(ex)); }
    finally { setBusy(false); }
  };
  const tf = (k: string, label: string, props: R = {}) => (
    <TextField label={label} value={f[k]} onChange={set(k)} error={!!errors[k]} helperText={errors[k]} fullWidth {...props} />
  );
  return (
    <Box component="form" onSubmit={submit}>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("first_name", "First name", { required: true })}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("last_name", "Last name", { required: true })}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("email", "Email", { required: true, type: "email" })}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("phone", "Phone (e.g. 024 123 4567)", { required: true })}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("location", "Town / city")}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("gender", "Gender", { select: true, children: [<MenuItem key="" value="">Prefer not to say</MenuItem>, <MenuItem key="f" value="female">Female</MenuItem>, <MenuItem key="m" value="male">Male</MenuItem>] })}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("highest_qualification", "Highest qualification", { required: true, select: true, children: qualifications.map((q) => <MenuItem key={q.value} value={q.value}>{q.label}</MenuItem>) })}</Grid>
        <Grid size={{ xs: 12, sm: 6 }}>{tf("field_of_study", "Field of study")}</Grid>
        <Grid size={{ xs: 12, sm: 4 }}>{tf("years_experience", "Years of relevant experience", { required: true, type: "number", inputProps: { min: 0, step: 0.5 } })}</Grid>
        <Grid size={{ xs: 12, sm: 4 }}>{tf("current_employer", "Current / last employer")}</Grid>
        <Grid size={{ xs: 12, sm: 4 }}>{tf("current_title", "Current / last job title")}</Grid>
        {(vacancy.questions || []).map((qn: R) => (
          <Grid key={qn.key} size={12}>
            <TextField fullWidth required={qn.required} label={qn.question} value={answers[qn.key] || ""} select={qn.type === "yes_no"}
              type={qn.type === "number" ? "number" : "text"} onChange={(e) => setAnswers({ ...answers, [qn.key]: e.target.value })}>
              {qn.type === "yes_no" && [<MenuItem key="y" value="yes">Yes</MenuItem>, <MenuItem key="n" value="no">No</MenuItem>]}
            </TextField>
          </Grid>
        ))}
        <Grid size={12}>{tf("cover_letter", "Cover letter (optional)", { multiline: true, minRows: 4 })}</Grid>
        <Grid size={12} sx={{ display: "none" }}>{tf("website", "Website")}</Grid>
        <Grid size={12}>
          <Button variant="outlined" component="label" fullWidth>{cv ? cv.name : "Attach your CV (PDF or Word, max 15 MB) *"}
            <input hidden type="file" accept=".pdf,.doc,.docx" onChange={(e) => setCv(e.target.files?.[0] || null)} /></Button>
        </Grid>
        <Grid size={12}>
          <FormControlLabel control={<Checkbox checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} />}
            label="I consent to the processing of my personal data for this recruitment, in line with the Data Protection Act, 2012 (Act 843). My details are kept for up to 12 months and then anonymised." />
          <FormControlLabel control={<Checkbox checked={f.talent_pool} onChange={(e) => setF({ ...f, talent_pool: e.target.checked })} />}
            label="Keep my details in your talent pool and contact me about future vacancies." />
        </Grid>
      </Grid>
      {err && <Alert severity="error" sx={{ my: 2 }}>{err}</Alert>}
      <Button type="submit" variant="contained" size="large" disabled={!f.consent || busy} sx={{ mt: 2 }}>{busy ? "Submitting…" : "Submit application"}</Button>
    </Box>
  );
}

export default function Careers() {
  const { org = "", id } = useParams();
  const list = useApi<R>(id ? null : `/public/careers/${org}/`);
  const one = useApi<R>(id ? `/public/careers/${org}/${id}/` : null);
  const q = id ? one : list;
  if (q.isLoading) return <PublicShell><Loading /></PublicShell>;
  if (!q.data) return <PublicShell><ErrorAlert error={q.error} /></PublicShell>;
  const orgName = q.data.organization?.name;
  if (id) {
    const v = q.data.vacancy;
    return (
      <PublicShell org={orgName}>
        <Button component={RouterLink} to={`/careers/${org}`} sx={{ mb: 1 }}>← All vacancies</Button>
        <Card sx={{ mb: 2 }}><CardContent>
          <Typography variant="h5" fontWeight={700}>{v.title}</Typography>
          <Stack direction="row" spacing={1} sx={{ my: 1.5 }} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={v.department} /><Chip size="small" label={v.employment_type} />
            {v.location && <Chip size="small" label={v.location} />}{v.salary_display && <Chip size="small" label={v.salary_display} />}
            {v.closing_date && <Chip size="small" color="warning" variant="outlined" label={`Apply by ${fmtDate(v.closing_date)}`} />}
          </Stack>
          <VacancyText v={v} />
        </CardContent></Card>
        <Card><CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Apply for this position</Typography>
          <ApplyForm org={org} vacancy={v} qualifications={q.data.qualifications} />
        </CardContent></Card>
      </PublicShell>
    );
  }
  return (
    <PublicShell org={orgName}>
      <Typography variant="h5" fontWeight={700} sx={{ mb: 2 }}>Current vacancies at {orgName}</Typography>
      {q.data.vacancies.length === 0 && <Card><Empty title="There are no open vacancies at the moment" hint="Please check back later." /></Card>}
      <Stack spacing={1.5}>
        {q.data.vacancies.map((v: R) => (
          <Card key={v.id}><CardActionArea component={RouterLink} to={`/careers/${org}/${v.id}`}><CardContent>
            <Typography variant="h6">{v.title}</Typography>
            <Typography variant="body2" color="text.secondary">{[v.department, v.location, v.employment_type].filter(Boolean).join(" · ")}
              {v.closing_date && ` · apply by ${fmtDate(v.closing_date)}`}</Typography>
            {v.summary && <Typography variant="body2" sx={{ mt: 1 }} noWrap>{v.summary}</Typography>}
          </CardContent></CardActionArea></Card>
        ))}
      </Stack>
    </PublicShell>
  );
}
