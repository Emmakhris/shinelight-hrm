import { Alert, Box, Button, Card, CardActions, CardContent, Checkbox, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, Grid2 as Grid, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { Empty, Loading, useToast } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { QUALIFICATIONS } from "../recruitment/constants";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function VacancyText({ v }: { v: R }) {
  return (
    <Stack spacing={1.5}>
      {v.summary && <Typography sx={{ whiteSpace: "pre-wrap" }}>{v.summary}</Typography>}
      {v.responsibilities && <Box><Typography variant="subtitle2">Responsibilities</Typography><Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{v.responsibilities}</Typography></Box>}
      {v.requirements && <Box><Typography variant="subtitle2">Requirements</Typography><Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{v.requirements}</Typography></Box>}
      <Typography variant="body2" color="text.secondary">Minimum: {v.min_qualification}{v.min_experience_years ? `, ${v.min_experience_years} years' experience` : ""}</Typography>
    </Stack>
  );
}

export default function InternalJobs() {
  const q = useApi<R>("/me/vacancies/");
  const [applying, setApplying] = useState<R | null>(null);
  const [form, setForm] = useState<R>({ highest_qualification: "degree", years_experience: "", cover_letter: "", consent: false, answers: {} });
  const [cv, setCv] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  if (q.isLoading) return <Loading />;
  const applied = new Set((q.data?.my_applications || []).map((a: R) => a.vacancy_id));
  const submit = async () => {
    setErr(null);
    const fd = new FormData();
    fd.append("vacancy", String(applying!.id));
    fd.append("highest_qualification", form.highest_qualification);
    fd.append("years_experience", String(form.years_experience || 0));
    fd.append("cover_letter", form.cover_letter);
    fd.append("consent", String(form.consent));
    fd.append("answers", JSON.stringify(form.answers));
    if (cv) fd.append("cv", cv);
    try {
      await api.post("/me/vacancies/", fd);
      toast.ok("Application submitted. HR will be in touch."); setApplying(null); inv("/me/vacancies");
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <>
      <PageHeader title="Internal job opportunities" subtitle="Vacancies open to current staff. Speak to your supervisor before applying." />
      {(q.data?.vacancies || []).length === 0 && <Card><Empty title="No internal vacancies right now" hint="New opportunities appear here as soon as they are published." /></Card>}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {(q.data?.vacancies || []).map((v: R) => (
          <Grid key={v.id} size={{ xs: 12, md: 6 }}>
            <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
              <CardContent sx={{ flex: 1 }}>
                <Typography variant="h6">{v.title}</Typography>
                <Stack direction="row" spacing={1} sx={{ my: 1 }} flexWrap="wrap">
                  <Chip size="small" label={v.department} /><Chip size="small" label={v.employment_type} />
                  {v.location && <Chip size="small" label={v.location} />}
                  {v.closing_date && <Chip size="small" color="warning" variant="outlined" label={`Closes ${fmtDate(v.closing_date)}`} />}
                </Stack>
                <VacancyText v={v} />
              </CardContent>
              <CardActions>
                {applied.has(v.id) ? <Chip label="Applied" color="success" /> :
                  <Button variant="contained" onClick={() => { setApplying(v); setErr(null); setForm((f) => ({ ...f, answers: {} })); }}>Apply</Button>}
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Section title="My applications" dense>
        <DataTable dense rows={q.data?.my_applications || []} emptyTitle="You have not applied for any internal vacancy"
          columns={[{ key: "reference", label: "Ref" }, { key: "vacancy", label: "Vacancy" }, { key: "stage", label: "Status" },
            { key: "applied_at", label: "Applied", render: (r) => fmtDate(r.applied_at) }]} />
      </Section>
      <Dialog open={!!applying} onClose={() => setApplying(null)} fullWidth maxWidth="sm">
        <DialogTitle>Apply — {applying?.title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info">Your name, contact details and current role are taken from your employee record.</Alert>
            <Stack direction="row" spacing={2}>
              <TextField select fullWidth label="Highest qualification" value={form.highest_qualification} onChange={(e) => setForm({ ...form, highest_qualification: e.target.value })}>
                {QUALIFICATIONS.map((x) => <MenuItem key={x.value} value={x.value}>{x.label}</MenuItem>)}
              </TextField>
              <TextField fullWidth type="number" label="Years' experience" value={form.years_experience} onChange={(e) => setForm({ ...form, years_experience: e.target.value })} />
            </Stack>
            {(applying?.questions || []).map((qn: R) => (
              qn.type === "yes_no" ? (
                <TextField key={qn.key} select label={qn.question} required={qn.required} value={form.answers[qn.key] || ""}
                  onChange={(e) => setForm({ ...form, answers: { ...form.answers, [qn.key]: e.target.value } })}>
                  <MenuItem value="yes">Yes</MenuItem><MenuItem value="no">No</MenuItem>
                </TextField>
              ) : <TextField key={qn.key} label={qn.question} required={qn.required} value={form.answers[qn.key] || ""} type={qn.type === "number" ? "number" : "text"}
                onChange={(e) => setForm({ ...form, answers: { ...form.answers, [qn.key]: e.target.value } })} />
            ))}
            <TextField label="Why are you interested in this role?" multiline minRows={3} value={form.cover_letter} onChange={(e) => setForm({ ...form, cover_letter: e.target.value })} />
            <Button variant="outlined" component="label">{cv ? cv.name : "Attach updated CV (optional)"}<input hidden type="file" accept=".pdf,.doc,.docx" onChange={(e) => setCv(e.target.files?.[0] || null)} /></Button>
            <FormControlLabel control={<Checkbox checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} />}
              label="I agree that HR may use my records and this application to assess my suitability." />
            {err && <Alert severity="error">{err}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setApplying(null)}>Cancel</Button><Button variant="contained" disabled={!form.consent} onClick={submit}>Submit application</Button></DialogActions>
      </Dialog>
    </>
  );
}
