import UploadFile from "@mui/icons-material/UploadFile";
import { Alert, Button, Chip, Grid2 as Grid, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { ErrorAlert, Loading, useToast } from "../../components/Feedback";
import { Field, Kpi, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const STATE: Record<string, { label: string; color: "success" | "info" | "warning" | "error" }> = {
  active: { label: "Active", color: "success" },
  evaluation: { label: "Evaluation", color: "info" },
  expiring: { label: "Expiring soon", color: "warning" },
  grace: { label: "Expired, in grace period", color: "warning" },
  expired: { label: "Expired, read-only", color: "error" },
  invalid: { label: "Invalid", color: "error" },
};

export default function Licence() {
  const { data, isLoading, error } = useApi<R>("/licence/");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const st = STATE[data.state] || { label: data.state, color: "info" as const };
  const install = async (body: string | FormData) => {
    setBusy(true);
    try {
      await api.post("/licence/", typeof body === "string" ? { licence: body } : body);
      toast.ok("Licence installed."); setText(""); inv("/licence/");
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  };
  const cap = Number(data.max_employees) || 0;
  return (
    <>
      <PageHeader title="Licence" subtitle="Your ShineLight HRM licence for this server." />
      {data.message && <Alert severity={st.color === "success" ? "info" : st.color} sx={{ mb: 2 }}>{data.message}</Alert>}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, md: 4 }}><Kpi label="Status" value={<Chip color={st.color} label={st.label} />} /></Grid>
        <Grid size={{ xs: 6, md: 4 }}><Kpi label="Active employees" value={data.active_employees} hint={cap ? `of ${cap} licensed` : "no limit"} /></Grid>
        <Grid size={{ xs: 6, md: 4 }}><Kpi label="Expires" value={data.expires ? fmtDate(data.expires) : "—"} hint={data.grace_ends ? `grace until ${fmtDate(data.grace_ends)}` : undefined} /></Grid>
      </Grid>
      {data.state !== "evaluation" && (
        <Section title="Licence details">
          <Stack spacing={1}>
            <Field label="Licensed to" value={data.customer || "—"} />
            <Field label="Licence number" value={data.licence_id || "—"} />
            <Field label="Modules" value={data.features ? <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>{(data.features as string[]).map((f) => <Chip key={f} size="small" label={f} />)}</Stack> : "All"} />
          </Stack>
        </Section>
      )}
      <Section title={data.state === "evaluation" ? "Install your licence" : "Install a renewed licence"}>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Your ShineLight provider sends the licence as a <code>.lic</code> file. Upload it, or paste its contents. It's checked
          on this server; nothing is sent anywhere.
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
          <Button variant="contained" component="label" startIcon={<UploadFile />} disabled={busy}>
            Upload licence file
            <input hidden type="file" accept=".lic,.txt" onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) { const fd = new FormData(); fd.append("file", f); install(fd); }
              e.target.value = "";
            }} />
          </Button>
        </Stack>
        <TextField fullWidth multiline minRows={4} label="…or paste the licence" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="-----BEGIN SHINELIGHT LICENCE-----" inputProps={{ style: { fontFamily: "monospace", fontSize: 12 } }} />
        <Button sx={{ mt: 1 }} variant="outlined" disabled={busy || !text.trim()} onClick={() => install(text)}>Install pasted licence</Button>
      </Section>
      <Alert severity="info">
        Expiry reminders go to administrators 60, 30 and 7 days before the licence ends. After it expires there is a grace period;
        after that the system becomes read-only (everyone can still sign in, view and export) until a renewal is installed.
      </Alert>
    </>
  );
}
