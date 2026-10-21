import { Alert, Box, Button, Card, CardContent, Checkbox, FormControlLabel, InputAdornment, Link, Stack, TextField, Typography } from "@mui/material";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import { useApi } from "../../api/hooks";

export default function Signup() {
  const info = useApi<{ enabled: boolean; base_domain: string }>("/public/signup/");
  const [f, setF] = useState({ organization_name: "", code: "", admin_name: "", email: "", username: "", password: "", accept_terms: false });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ login_url: string; trial_ends_at: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try { setDone((await api.post("/public/signup/", f)).data); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  };
  const suffix = info.data?.base_domain ? `.${info.data.base_domain}` : "";
  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center", p: 2, background: "linear-gradient(135deg, #0f3d5e 0%, #155e75 60%, #f5b700 160%)" }}>
      <Card sx={{ width: "100%", maxWidth: 520, borderRadius: 3 }} elevation={8}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h5" fontWeight={700} gutterBottom>Start your ShineLight HRM trial</Typography>
          {info.data && !info.data.enabled && <Alert severity="info">Self-service sign-up isn't available. Please contact us to set up your organization.</Alert>}
          {done && (
            <Alert severity="success">
              Your organization is ready{done.trial_ends_at ? ` (trial until ${done.trial_ends_at.split("-").reverse().join("/")})` : ""}. Sign in at{" "}
              <Link href={done.login_url}>{done.login_url}</Link>
            </Alert>
          )}
          {info.data?.enabled && !done && (
            <form onSubmit={submit}>
              <Stack spacing={2}>
                {error && <Alert severity="error">{error}</Alert>}
                <TextField label="Organization name" value={f.organization_name} onChange={(e) => set("organization_name", e.target.value)} required />
                <TextField label="Your address" value={f.code} onChange={(e) => set("code", e.target.value.toLowerCase())} required
                  helperText="Lowercase letters, numbers and hyphens" InputProps={{ endAdornment: suffix ? <InputAdornment position="end">{suffix}</InputAdornment> : undefined }} />
                <TextField label="Your full name" value={f.admin_name} onChange={(e) => set("admin_name", e.target.value)} required />
                <TextField label="Work email" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} required />
                <TextField label="Username" value={f.username} onChange={(e) => set("username", e.target.value)} required />
                <TextField label="Password" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} required helperText="At least 10 characters" autoComplete="new-password" />
                <FormControlLabel control={<Checkbox checked={f.accept_terms} onChange={(e) => set("accept_terms", e.target.checked)} />}
                  label="I accept the terms of service and the data processing agreement (Data Protection Act, 2012 (Act 843))." />
                <Button type="submit" variant="contained" size="large" disabled={busy || !f.accept_terms}>Create my organization</Button>
                <Link href="/login" variant="body2">Already have an account? Sign in</Link>
              </Stack>
            </form>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
