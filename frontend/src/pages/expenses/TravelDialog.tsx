import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid, MenuItem, TextField } from "@mui/material";
import { useEffect, useState } from "react";
import { api, errorMessage } from "../../api/client";
import { useInvalidate } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { fmtMoney } from "../../utils";

const DEST = [["local", "Within my region"], ["national", "Another region in Ghana"], ["africa", "Elsewhere in Africa"], ["international", "Outside Africa"]];
const MODES = [["road_official", "Official vehicle"], ["road_public", "Public transport"], ["road_private", "Own vehicle"], ["air", "Air"], ["other", "Other"]];

export default function TravelDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [v, setV] = useState<Record<string, string>>({ destination_class: "national", transport_mode: "road_public", transport_estimate: "0",
    accommodation_estimate: "0", other_estimate: "0", advance_requested: "0", purpose: "", destination: "", departure_date: "", return_date: "" });
  const [est, setEst] = useState<{ per_diem_days: string; per_diem_rate: string; currency: string; total_estimate: string; warnings: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  const set = (k: string, x: string) => setV((s) => ({ ...s, [k]: x }));
  useEffect(() => {
    if (!v.departure_date || !v.return_date || !v.destination || !v.purpose) { setEst(null); return; }
    const t = setTimeout(async () => {
      try { setEst((await api.post("/expenses/travel/estimate/", v)).data); setError(null); } catch (e) { setError(errorMessage(e)); }
    }, 400);
    return () => clearTimeout(t);
  }, [v]);
  const submit = async () => {
    try {
      await api.post("/expenses/travel/", { ...v, submit: true });
      toast.ok("Travel request submitted."); inv("/expenses/", "/workflow/"); onClose();
    } catch (e) { setError(errorMessage(e)); }
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Official travel request</DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Grid container spacing={2}>
          <Grid size={12}><TextField fullWidth required label="Purpose of travel" multiline minRows={2} value={v.purpose} onChange={(e) => set("purpose", e.target.value)} /></Grid>
          <Grid size={{ xs: 12, md: 6 }}><TextField fullWidth required label="Destination (city, country)" value={v.destination} onChange={(e) => set("destination", e.target.value)} /></Grid>
          <Grid size={{ xs: 12, md: 6 }}><TextField select fullWidth label="Destination type" value={v.destination_class} onChange={(e) => set("destination_class", e.target.value)}>
            {DEST.map(([a, b]) => <MenuItem key={a} value={a}>{b}</MenuItem>)}</TextField></Grid>
          <Grid size={{ xs: 6, md: 4 }}><TextField fullWidth required type="date" label="Departure" InputLabelProps={{ shrink: true }} value={v.departure_date} onChange={(e) => set("departure_date", e.target.value)} /></Grid>
          <Grid size={{ xs: 6, md: 4 }}><TextField fullWidth required type="date" label="Return" InputLabelProps={{ shrink: true }} value={v.return_date} onChange={(e) => set("return_date", e.target.value)} /></Grid>
          <Grid size={{ xs: 12, md: 4 }}><TextField select fullWidth label="Transport" value={v.transport_mode} onChange={(e) => set("transport_mode", e.target.value)}>
            {MODES.map(([a, b]) => <MenuItem key={a} value={a}>{b}</MenuItem>)}</TextField></Grid>
          {[["transport_estimate", "Transport estimate"], ["accommodation_estimate", "Accommodation estimate"], ["other_estimate", "Other costs"], ["advance_requested", "Advance requested"]].map(([k, l]) => (
            <Grid key={k} size={{ xs: 6, md: 3 }}><TextField fullWidth type="number" label={l} value={v[k]} onChange={(e) => set(k, e.target.value)} /></Grid>
          ))}
        </Grid>
        {est && (
          <Alert severity="info" sx={{ mt: 2 }}>
            Per diem: {Number(est.per_diem_days)} day(s) × {fmtMoney(est.per_diem_rate, est.currency)} · <b>Total estimate {fmtMoney(est.total_estimate, est.currency)}</b>
          </Alert>
        )}
        {est?.warnings.map((w) => <Alert key={w} severity="warning" sx={{ mt: 1 }}>{w}</Alert>)}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!est} onClick={submit}>Submit for approval</Button>
      </DialogActions>
    </Dialog>
  );
}
