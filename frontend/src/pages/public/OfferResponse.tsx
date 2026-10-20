import { Alert, Box, Button, Card, CardContent, Checkbox, FormControlLabel, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useApi } from "../../api/hooks";
import { ErrorAlert, Loading } from "../../components/Feedback";
import { Field } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";
import { PublicShell } from "./Careers";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function OfferResponse() {
  const { token = "" } = useParams();
  const q = useApi<R>(`/public/offers/${token}/`);
  const [mode, setMode] = useState<null | "accept" | "decline" | "negotiate">(null);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [agree, setAgree] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  if (q.isLoading) return <PublicShell><Loading /></PublicShell>;
  if (!q.data) return <PublicShell><ErrorAlert error={q.error} /></PublicShell>;
  const o = q.data;
  const open = ["sent", "negotiating"].includes(o.status) && !o.expired;
  const viewLetter = async () => {
    const res = await api.get(`/public/offers/${token}/`, { params: { letter: 1 }, responseType: "blob" });
    window.open(URL.createObjectURL(res.data as Blob), "_blank", "noopener");
  };
  const respond = async () => {
    setErr(null);
    try {
      const r = await api.post(`/public/offers/${token}/`, { decision: mode, typed_name: name, note });
      setResult(r.data.status); q.refetch();
    } catch (e) { setErr(errorMessage(e)); }
  };
  const total = Number(o.basic_salary) + (o.allowances || []).reduce((a: number, x: R) => a + Number(x.amount || 0), 0);
  return (
    <PublicShell org={o.organization}>
      <Card><CardContent>
        <Typography variant="h5" fontWeight={700}>Offer of employment</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Dear {o.candidate_name}, please review your offer ({o.reference}, revision {o.revision}).</Typography>
        <Stack spacing={1} sx={{ mb: 2 }}>
          <Field label="Position" value={`${o.job_title}, ${o.department}`} />
          <Field label="Employment type" value={o.employment_type} />
          <Field label="Start date" value={fmtDate(o.start_date)} />
          <Field label="Monthly basic salary" value={fmtMoney(o.basic_salary)} />
          {(o.allowances || []).map((a: R) => <Field key={a.name} label={a.name} value={fmtMoney(a.amount)} />)}
          {o.allowances?.length > 0 && <Field label="Total monthly (before tax and SSNIT)" value={<b>{fmtMoney(total)}</b>} />}
          {o.probation_months > 0 && <Field label="Probation" value={`${o.probation_months} months`} />}
          <Field label="Respond by" value={fmtDate(o.expiry_date)} />
        </Stack>
        <Button variant="outlined" onClick={viewLetter} sx={{ mb: 2 }}>Read the full offer letter (PDF)</Button>
        {result === "accepted" || o.status === "accepted" ? <Alert severity="success">Thank you for accepting. HR will contact you about your first day and pre-employment documents.</Alert>
          : o.status === "declined" ? <Alert severity="info">You declined this offer. Thank you for letting us know.</Alert>
          : o.expired || o.status === "expired" ? <Alert severity="warning">This offer has expired. Please contact the recruitment team.</Alert>
          : o.status === "negotiating" && result === "negotiating" ? <Alert severity="info">Your message was sent to the recruitment team, who will respond shortly.</Alert>
          : null}
        {open && result !== "accepted" && (
          <Box>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
              <Button variant={mode === "accept" ? "contained" : "outlined"} color="success" onClick={() => setMode("accept")}>Accept offer</Button>
              <Button variant={mode === "negotiate" ? "contained" : "outlined"} onClick={() => setMode("negotiate")}>Discuss terms</Button>
              <Button variant={mode === "decline" ? "contained" : "outlined"} color="error" onClick={() => setMode("decline")}>Decline</Button>
            </Stack>
            {mode === "accept" && <Stack spacing={1.5}>
              <Typography variant="body2">To accept, type your full name as it appears above (<b>{o.candidate_name}</b>). This is recorded as your electronic signature with the date and time.</Typography>
              <TextField label="Full name" value={name} onChange={(e) => setName(e.target.value)} />
              <FormControlLabel control={<Checkbox checked={agree} onChange={(e) => setAgree(e.target.checked)} />} label="I have read the offer letter and accept the terms and conditions." />
              <Button variant="contained" color="success" disabled={!agree || !name.trim()} onClick={respond}>Confirm acceptance</Button>
            </Stack>}
            {mode && mode !== "accept" && <Stack spacing={1.5}>
              <TextField label={mode === "negotiate" ? "What would you like to discuss?" : "Reason (optional)"} value={note} onChange={(e) => setNote(e.target.value)} multiline minRows={3} />
              <Button variant="contained" color={mode === "decline" ? "error" : "primary"} onClick={respond}>{mode === "decline" ? "Decline offer" : "Send message"}</Button>
            </Stack>}
            {err && <Alert severity="error" sx={{ mt: 2 }}>{err}</Alert>}
          </Box>
        )}
      </CardContent></Card>
    </PublicShell>
  );
}
