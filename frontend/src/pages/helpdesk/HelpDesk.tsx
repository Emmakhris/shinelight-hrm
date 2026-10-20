import Add from "@mui/icons-material/Add";
import MenuBook from "@mui/icons-material/MenuBook";
import { Alert, Box, Button, Card, CardActionArea, CardContent, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid,
  Link, List, ListItemButton, ListItemText, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDateTime } from "../../utils";

interface Service { id: number; name: string; description: string; category: number; category_name: string; self_service: boolean;
  is_active: boolean; is_confidential: boolean; form_fields: { name: string; label: string; required?: boolean }[]; resolution_sla_hours: number }
interface Category { id: number; name: string; code: string }

export function NewRequestDialog({ open, onClose, employee }: { open: boolean; onClose: () => void; employee?: number }) {
  const cats = useList<Category>(open ? "/helpdesk/categories/" : null);
  const services = useList<Service>(open ? "/helpdesk/services/" : null, { is_active: "true" });
  const { can } = useAuth();
  const [cat, setCat] = useState<number | null>(null);
  const [svc, setSvc] = useState<Service | null>(null);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [channel, setChannel] = useState("portal");
  const [suggest, setSuggest] = useState<{ id: number; title: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  const inv = useInvalidate();
  const toast = useToast();
  const agent = can("servicedesk.agent");
  useEffect(() => { if (!open) { setCat(null); setSvc(null); setSubject(""); setDescription(""); setForm({}); setError(null); } }, [open]);
  useEffect(() => {
    const q = `${subject} ${description}`.trim();
    if (q.length < 6) { setSuggest([]); return; }
    const t = setTimeout(async () => setSuggest((await api.get("/helpdesk/articles/suggest/", { params: { q } })).data), 400);
    return () => clearTimeout(t);
  }, [subject, description]);
  const submit = async () => {
    setError(null);
    try {
      const { data } = await api.post("/helpdesk/tickets/", { service_type: svc!.id, subject: subject || svc!.name, description,
        form_data: form, employee, channel: agent ? channel : "portal" });
      toast.ok(`Request ${data.reference} submitted.`);
      inv("/helpdesk/");
      onClose();
      nav(`/helpdesk/tickets/${data.id}`);
    } catch (e) { setError(errorMessage(e)); }
  };
  const visible = services.items.filter((s) => (agent || s.self_service) && (!cat || s.category === cat));
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{svc ? svc.name : "What do you need help with?"}</DialogTitle>
      <DialogContent dividers>
        {!svc ? (
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 4 }}>
              <List dense>
                <ListItemButton selected={!cat} onClick={() => setCat(null)}><ListItemText primary="All services" /></ListItemButton>
                {cats.items.map((c) => <ListItemButton key={c.id} selected={cat === c.id} onClick={() => setCat(c.id)}><ListItemText primary={c.name} /></ListItemButton>)}
              </List>
            </Grid>
            <Grid size={{ xs: 12, md: 8 }}>
              <Stack spacing={1}>
                {visible.map((s) => (
                  <Card key={s.id}><CardActionArea onClick={() => { setSvc(s); setSubject(s.name); }}>
                    <CardContent sx={{ py: 1.5 }}>
                      <Typography fontWeight={650}>{s.name}</Typography>
                      <Typography variant="body2" color="text.secondary">{s.description}</Typography>
                      <Typography variant="caption" color="text.secondary">{s.category_name} · usually resolved within {Math.round(s.resolution_sla_hours / 24 * 10) / 10} day(s)</Typography>
                    </CardContent>
                  </CardActionArea></Card>
                ))}
              </Stack>
            </Grid>
          </Grid>
        ) : (
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            {svc.is_confidential && <Alert severity="info">This request is confidential: only the assigned HR officer and desk managers can see it.</Alert>}
            <TextField label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} required />
            {svc.form_fields.map((f) => (
              <TextField key={f.name} label={f.label} required={f.required} value={form[f.name] || ""}
                onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />
            ))}
            <TextField label="Details" value={description} onChange={(e) => setDescription(e.target.value)} multiline minRows={4} required />
            {agent && (
              <TextField select label="Received via" value={channel} onChange={(e) => setChannel(e.target.value)}>
                {[["portal", "Portal"], ["phone", "Phone"], ["email", "Email"], ["walk_in", "Walk-in"]].map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
              </TextField>
            )}
            {suggest.length > 0 && (
              <Alert severity="info" icon={<MenuBook />}>These articles may answer your question:{" "}
                {suggest.map((a, i) => <span key={a.id}>{i > 0 && " · "}<Link href={`/helpdesk/kb?article=${a.id}`} target="_blank">{a.title}</Link></span>)}
              </Alert>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {svc && <Button onClick={() => setSvc(null)}>Back</Button>}
        <Box flex={1} />
        <Button onClick={onClose}>Cancel</Button>
        {svc && <Button variant="contained" disabled={!description.trim()} onClick={submit}>Submit request</Button>}
      </DialogActions>
    </Dialog>
  );
}

export default function HelpDesk() {
  const [open, setOpen] = useState(false);
  const { items, isLoading } = useList("/helpdesk/tickets/", { view: "mine" });
  const nav = useNavigate();
  return (
    <>
      <PageHeader title="HR help desk" subtitle="Ask HR for a letter, raise a payroll query, or get help — and track it to resolution."
        actions={<>
          <Button startIcon={<MenuBook />} onClick={() => nav("/helpdesk/kb")}>Knowledge base</Button>
          <Button variant="contained" startIcon={<Add />} onClick={() => setOpen(true)}>New request</Button>
        </>} />
      <Section title="My requests" dense>
        <DataTable loading={isLoading} rows={items} onRowClick={(r) => nav(`/helpdesk/tickets/${r.id}`)} emptyTitle="No requests yet"
          columns={[{ key: "reference", label: "Reference" }, { key: "subject", label: "Subject" },
            { key: "service_name", label: "Service", hideOnMobile: true },
            { key: "assignee_name", label: "Handled by", hideOnMobile: true },
            { key: "created_at", label: "Raised", render: (r) => fmtDateTime(r.created_at) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]} />
      </Section>
      <NewRequestDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}
