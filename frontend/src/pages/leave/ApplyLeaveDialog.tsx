import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Grid2 as Grid,
  MenuItem, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { api, errorMessage } from "../../api/client";
import { useInvalidate, useList } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { fmtDate } from "../../utils";

interface Preview { days: string; warnings: string[]; error: string | null; balance: { available: string } | null; expected_return_date: string | null }

export default function ApplyLeaveDialog({ open, onClose, employee }: { open: boolean; onClose: () => void; employee?: number }) {
  const types = useList<{ id: number; name: string; requires_attachment: boolean; attachment_after_days: number; allow_half_day: boolean; is_active: boolean }>("/leave/types/");
  const colleagues = useList<{ id: number; full_name: string }>(open ? "/directory/" : null);
  const [v, setV] = useState({ leave_type: "", start_date: "", end_date: "", start_half: false, end_half: false, reason: "",
    contact_while_away: "", relief_officer: "" });
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  const lt = types.items.find((t) => String(t.id) === String(v.leave_type));
  const set = (k: string, val: unknown) => setV((s) => ({ ...s, [k]: val }));

  useEffect(() => {
    if (!v.leave_type || !v.start_date || !v.end_date) { setPreview(null); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.post<Preview>("/leave/requests/preview/", { ...v, employee, relief_officer: v.relief_officer || null });
        setPreview(data);
      } catch (e) { setPreview({ days: "0", warnings: [], error: errorMessage(e), balance: null, expected_return_date: null }); }
    }, 350);
    return () => clearTimeout(t);
  }, [v, employee]);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      let attachment: number | null = null;
      if (file) {
        const cats = (await api.get("/documents/categories/")).data as { id: number; code: string }[];
        const cat = cats.find((c) => c.code === "medical") || cats.find((c) => c.code === "other") || cats[0];
        const fd = new FormData();
        fd.append("file", file); fd.append("title", `Leave supporting document — ${file.name}`); fd.append("category", String(cat.id));
        fd.append("confidentiality", lt?.name.toLowerCase().includes("sick") ? "restricted" : "confidential");
        if (employee) fd.append("employee", String(employee));
        attachment = (await api.post("/documents/", fd)).data.id;
      }
      await api.post("/leave/requests/", { ...v, employee, relief_officer: v.relief_officer || null, attachment, submit: true });
      toast.ok("Leave request submitted for approval.");
      inv("/leave/", "/me/", "/workflow/");
      onClose();
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };

  const needsFile = lt?.requires_attachment && preview && Number(preview.days) > lt.attachment_after_days;
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Apply for leave</DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Grid container spacing={2}>
          <Grid size={12}>
            <TextField select fullWidth required label="Leave type" value={v.leave_type} onChange={(e) => set("leave_type", e.target.value)}>
              {types.items.filter((t) => t.is_active).map((t) => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={6}><TextField fullWidth required type="date" label="First day" InputLabelProps={{ shrink: true }} value={v.start_date} onChange={(e) => set("start_date", e.target.value)} /></Grid>
          <Grid size={6}><TextField fullWidth required type="date" label="Last day" InputLabelProps={{ shrink: true }} value={v.end_date} onChange={(e) => set("end_date", e.target.value)} /></Grid>
          {lt?.allow_half_day && (
            <Grid size={12}>
              <FormControlLabel control={<Checkbox checked={v.start_half} onChange={(e) => set("start_half", e.target.checked)} />} label="Start in the afternoon" />
              <FormControlLabel control={<Checkbox checked={v.end_half} onChange={(e) => set("end_half", e.target.checked)} />} label="Finish at midday" />
            </Grid>
          )}
          <Grid size={12}>
            <TextField select fullWidth label="Relief officer (covers your duties)" value={v.relief_officer} onChange={(e) => set("relief_officer", e.target.value)}>
              <MenuItem value="">None</MenuItem>
              {colleagues.items.map((c) => <MenuItem key={c.id} value={c.id}>{c.full_name}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={12}><TextField fullWidth label="Reason" multiline minRows={2} value={v.reason} onChange={(e) => set("reason", e.target.value)} /></Grid>
          <Grid size={12}><TextField fullWidth label="Contact while away" value={v.contact_while_away} onChange={(e) => set("contact_while_away", e.target.value)} /></Grid>
          {(lt?.requires_attachment) && (
            <Grid size={12}>
              <Button component="label" variant="outlined" fullWidth color={needsFile && !file ? "warning" : "primary"}>
                {file ? file.name : `Attach supporting document${needsFile ? " (required)" : ""}`}
                <input hidden type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </Button>
              <Typography variant="caption" color="text.secondary">Medical details are visible only to authorised HR staff.</Typography>
            </Grid>
          )}
        </Grid>
        {preview && (
          <Box sx={{ mt: 2 }}>
            {preview.error ? <Alert severity="error">{preview.error}</Alert> : (
              <Alert severity="info">
                <b>{Number(preview.days)} working day(s)</b>
                {preview.balance && <> · {Number(preview.balance.available)} available</>}
                {preview.expected_return_date && <> · back at work {fmtDate(preview.expected_return_date)}</>}
              </Alert>
            )}
            {preview.warnings.map((w) => <Alert key={w} severity="warning" sx={{ mt: 1 }}>{w}</Alert>)}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={busy || !preview || !!preview.error || (!!needsFile && !file)} onClick={submit}>Submit request</Button>
      </DialogActions>
    </Dialog>
  );
}
