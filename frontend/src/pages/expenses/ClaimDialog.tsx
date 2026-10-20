import Add from "@mui/icons-material/Add";
import AttachFile from "@mui/icons-material/AttachFile";
import Delete from "@mui/icons-material/DeleteOutline";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid, IconButton, MenuItem, Stack, Table,
  TableBody, TableCell, TableHead, TableRow, TextField, Tooltip, Typography } from "@mui/material";
import dayjs from "dayjs";
import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import { useInvalidate, useList } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { fmtMoney } from "../../utils";

export const CATEGORIES = [["transport", "Transport / fares"], ["fuel", "Fuel & mileage"], ["accommodation", "Accommodation"],
  ["meals", "Meals"], ["per_diem", "Per diem"], ["communication", "Airtime / data"], ["medical", "Medical"],
  ["training", "Training / conference fees"], ["supplies", "Office supplies"], ["other", "Other"]];

interface Item { date: string; category: string; description: string; amount: string; file?: File | null; receipt?: number | null; receipt_missing_reason: string }
const blank = (): Item => ({ date: dayjs().format("YYYY-MM-DD"), category: "transport", description: "", amount: "", file: null, receipt_missing_reason: "" });

export default function ClaimDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const trips = useList<{ id: number; reference: string; destination: string; advance_paid: string; status: string; claim_status: unknown }>(
    open ? "/expenses/travel/" : null, { mine: 1 });
  const [title, setTitle] = useState("");
  const [trip, setTrip] = useState("");
  const [method, setMethod] = useState("payroll");
  const [items, setItems] = useState<Item[]>([blank()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inv = useInvalidate();
  const toast = useToast();
  const total = items.reduce((s, i) => s + (Number(i.amount) || 0), 0);
  const tripObj = trips.items.find((t) => String(t.id) === trip);
  const advance = tripObj ? Number(tripObj.advance_paid) : 0;
  const set = (i: number, patch: Partial<Item>) => setItems(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const cats = (await api.get("/documents/categories/")).data as { id: number; code: string }[];
      const cat = cats.find((c) => c.code === "other") || cats[0];
      const payloadItems = [];
      for (const it of items) {
        let receipt = it.receipt || null;
        if (it.file) {
          const fd = new FormData();
          fd.append("file", it.file); fd.append("title", `Receipt — ${it.description}`); fd.append("category", String(cat.id));
          fd.append("confidentiality", "confidential");
          receipt = (await api.post("/documents/", fd)).data.id;
        }
        payloadItems.push({ date: it.date, category: it.category, description: it.description, amount: it.amount, receipt,
          receipt_missing_reason: it.receipt_missing_reason });
      }
      await api.post("/expenses/claims/", { title, travel_request: trip || null, payment_method: method, items: payloadItems, submit: true });
      toast.ok("Claim submitted for approval.");
      inv("/expenses/", "/workflow/");
      setItems([blank()]); setTitle(""); setTrip("");
      onClose();
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg">
      <DialogTitle>New expense claim</DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 12, md: 5 }}><TextField fullWidth required label="Title (e.g. Kumasi audit trip)" value={title} onChange={(e) => setTitle(e.target.value)} /></Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField select fullWidth label="Retire a travel advance (optional)" value={trip} onChange={(e) => setTrip(e.target.value)}>
              <MenuItem value="">Not linked to a trip</MenuItem>
              {trips.items.filter((t) => ["approved", "completed"].includes(t.status) && !t.claim_status).map((t) =>
                <MenuItem key={t.id} value={t.id}>{t.reference} — {t.destination}{Number(t.advance_paid) ? ` (advance ${fmtMoney(t.advance_paid)})` : ""}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <TextField select fullWidth label="Reimburse via" value={method} onChange={(e) => setMethod(e.target.value)}>
              <MenuItem value="payroll">Next salary</MenuItem><MenuItem value="bank">Bank / MoMo transfer</MenuItem><MenuItem value="cash">Petty cash</MenuItem>
            </TextField>
          </Grid>
        </Grid>
        <Table size="small">
          <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Category</TableCell><TableCell>Description</TableCell>
            <TableCell align="right">Amount</TableCell><TableCell>Receipt</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {items.map((it, i) => (
              <TableRow key={i}>
                <TableCell><TextField type="date" value={it.date} onChange={(e) => set(i, { date: e.target.value })} /></TableCell>
                <TableCell><TextField select value={it.category} onChange={(e) => set(i, { category: e.target.value })} sx={{ minWidth: 150 }}>
                  {CATEGORIES.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField></TableCell>
                <TableCell><TextField fullWidth value={it.description} onChange={(e) => set(i, { description: e.target.value })} /></TableCell>
                <TableCell><TextField type="number" value={it.amount} onChange={(e) => set(i, { amount: e.target.value })} sx={{ width: 110 }} inputProps={{ step: "0.01" }} /></TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Tooltip title={it.file ? it.file.name : "Attach receipt"}>
                      <IconButton component="label" color={it.file ? "success" : "default"}><AttachFile fontSize="small" />
                        <input hidden type="file" accept="image/*,.pdf" onChange={(e) => set(i, { file: e.target.files?.[0] || null })} /></IconButton>
                    </Tooltip>
                    {!it.file && Number(it.amount) > 50 && <TextField placeholder="No receipt? Why" value={it.receipt_missing_reason}
                      onChange={(e) => set(i, { receipt_missing_reason: e.target.value })} sx={{ minWidth: 150 }} />}
                  </Stack>
                </TableCell>
                <TableCell><IconButton onClick={() => setItems(items.filter((_, j) => j !== i))} disabled={items.length === 1}><Delete fontSize="small" /></IconButton></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Button startIcon={<Add />} onClick={() => setItems([...items, blank()])} sx={{ mt: 1 }}>Add item</Button>
        <Stack alignItems="flex-end" sx={{ mt: 2 }}>
          <Typography>Total claimed: <b>{fmtMoney(total)}</b></Typography>
          {advance > 0 && <Typography>Less advance received: {fmtMoney(advance)}</Typography>}
          {advance > 0 && <Typography fontWeight={700} color={total - advance < 0 ? "error" : "success.main"}>
            {total - advance < 0 ? `You will refund ${fmtMoney(advance - total)} (recovered from salary)` : `Payable to you: ${fmtMoney(total - advance)}`}</Typography>}
          <Typography variant="caption" color="text.secondary">Receipts are required for items above GHS 50.</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={busy || !title || items.some((i) => !i.description || !i.amount)} onClick={submit}>Submit claim</Button>
      </DialogActions>
    </Dialog>
  );
}
