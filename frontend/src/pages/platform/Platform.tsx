import Add from "@mui/icons-material/Add";
import Logout from "@mui/icons-material/Logout";
import {
  Alert, AppBar, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel,
  Grid2 as Grid, Link, MenuItem, Stack, Switch, Tab, Tabs, TextField, Toolbar, Typography,
} from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const STATUS_COLOR: Record<string, "success" | "info" | "warning" | "default"> = { active: "success", trial: "info", suspended: "warning", cancelled: "default" };

function OrgDialog({ org, plans, onClose }: { org: R; plans: R[]; onClose: () => void }) {
  const toast = useToast();
  const inv = useInvalidate();
  const [form, setForm] = useState<R>({ plan: org.plan ?? "", trial_ends_at: org.trial_ends_at ?? "", domain: org.domain ?? "" });
  const [current, setCurrent] = useState<R>(org);
  const run = async (fn: () => Promise<{ data: R }>, msg: string) => {
    try { const { data } = await fn(); setCurrent(data); toast.ok(msg); inv("/platform/"); } catch (e) { toast.error(e); }
  };
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{current.name} <Chip size="small" sx={{ ml: 1 }} color={STATUS_COLOR[current.status]} label={current.status} /></DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Sign-in address: <Link href={current.login_url} target="_blank" rel="noopener">{current.login_url}</Link>
          {current.suspended_reason && ` · Suspended: ${current.suspended_reason}`}
        </Typography>
        <Grid container spacing={2} sx={{ my: 1 }}>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Active employees" value={current.usage.active_employees} hint={current.usage.employee_limit ? `of ${current.usage.employee_limit}` : "no limit"} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Users" value={current.usage.users} /></Grid>
          <Grid size={{ xs: 12, md: 6 }}><Kpi label="Last sign-in" value={current.usage.last_login ? fmtDateTime(current.usage.last_login) : "Never"} /></Grid>
        </Grid>
        <Divider sx={{ my: 2 }}>Subscription</Divider>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField select fullWidth size="small" label="Plan" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}
              helperText="Features outside the new plan are switched off.">
              <MenuItem value="">No plan (unlimited)</MenuItem>
              {plans.map((p) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 6, md: 4 }}><TextField fullWidth size="small" type="date" label="Trial ends" InputLabelProps={{ shrink: true }} value={form.trial_ends_at} onChange={(e) => setForm({ ...form, trial_ends_at: e.target.value })} /></Grid>
          <Grid size={{ xs: 6, md: 4 }}><TextField fullWidth size="small" label="Custom domain (optional)" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} /></Grid>
        </Grid>
        <Button sx={{ mt: 1 }} variant="outlined" onClick={() => run(() => api.patch(`/platform/organizations/${org.id}/`, { plan: form.plan || null, trial_ends_at: form.trial_ends_at || null, domain: form.domain }), "Subscription updated.")}>Save subscription</Button>
        <Divider sx={{ my: 2 }}>Features</Divider>
        <Grid container>
          {(current.features as R[]).map((f) => (
            <Grid key={f.code} size={{ xs: 12, sm: 6 }}>
              <FormControlLabel label={`${f.label}${f.in_plan ? "" : " (not in plan)"}`} disabled={!f.in_plan && !f.enabled}
                control={<Switch checked={f.enabled} onChange={(e) => run(() => api.post(`/platform/organizations/${org.id}/feature/`, { code: f.code, enabled: e.target.checked }), "Feature updated.")} />} />
            </Grid>))}
        </Grid>
        <Alert severity="info" sx={{ mt: 2 }}>Platform operators manage subscriptions only. Employee records, payroll and other HR data stay inside the organization, and every change here appears in the organization's own audit trail.</Alert>
      </DialogContent>
      <DialogActions>
        {current.is_active
          ? <Button color="warning" onClick={() => { const reason = window.prompt("Reason for suspending (kept on the record; users only see that access is suspended):"); if (reason !== null) run(() => api.post(`/platform/organizations/${org.id}/status/`, { status: "suspended", reason }), "Organization suspended."); }}>Suspend</Button>
          : <Button color="success" onClick={() => run(() => api.post(`/platform/organizations/${org.id}/status/`, { status: "active" }), "Organization reactivated.")}>Reactivate</Button>}
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function Platform() {
  const { me, logout } = useAuth();
  const [tab, setTab] = useState(0);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<R | null>(null);
  const orgs = useApi<R[]>("/platform/organizations/");
  const plans = useApi<R[]>("/platform/plans/");
  const inv = useInvalidate();
  const toast = useToast();
  const rows = orgs.data || [];
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="static" color="primary" elevation={0}>
        <Toolbar>
          <Typography variant="h6" sx={{ flex: 1 }}>ShineLight HRM · Platform</Typography>
          <Typography variant="body2" sx={{ mr: 2 }}>{me?.full_name}</Typography>
          <Button color="inherit" startIcon={<Logout />} onClick={logout}>Sign out</Button>
        </Toolbar>
      </AppBar>
      <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1280, mx: "auto" }}>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Organizations" value={rows.length} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="On trial" value={rows.filter((o) => o.status === "trial").length} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Suspended" value={rows.filter((o) => !o.is_active).length} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Kpi label="Active employees (all)" value={rows.reduce((n, o) => n + o.usage.active_employees, 0)} /></Grid>
        </Grid>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Organizations" /><Tab label="Plans" /></Tabs>
        {tab === 0 && (
          <Card>
            <Stack direction="row" justifyContent="flex-end" sx={{ p: 1.5 }}>
              <Button variant="contained" startIcon={<Add />} onClick={() => setCreating(true)}>New organization</Button>
            </Stack>
            <DataTable rows={rows} loading={orgs.isLoading} onRowClick={(r) => setOpen(r)} emptyTitle="No organizations yet" columns={[
              { key: "name", label: "Organization", render: (r) => <><Typography variant="body2" fontWeight={600} component="span">{r.name}</Typography><Typography variant="caption" color="text.secondary" component="span" display="block">{r.code}</Typography></> },
              { key: "status", label: "Status", render: (r) => <Chip size="small" color={STATUS_COLOR[r.status]} label={r.status} /> },
              { key: "plan_name", label: "Plan", render: (r) => r.plan_name || "—" },
              { key: "employees", label: "Employees", align: "right", render: (r) => `${r.usage.active_employees}${r.usage.employee_limit ? ` / ${r.usage.employee_limit}` : ""}` },
              { key: "users", label: "Users", align: "right", render: (r) => r.usage.users },
              { key: "trial_ends_at", label: "Trial ends", render: (r) => (r.trial_ends_at ? fmtDate(r.trial_ends_at) : "—") },
              { key: "last", label: "Last sign-in", render: (r) => (r.usage.last_login ? fmtDateTime(r.usage.last_login) : "Never") },
            ]} />
          </Card>
        )}
        {tab === 1 && (
          <Card>
            <ResourcePage embedded title="Plan" url="/platform/plans/" searchable={false} canDelete
              intro="Prices are in GHS per month. A plan's features are the modules organizations on it can switch on; 0 employees means no limit."
              columns={[{ key: "name", label: "Plan" }, { key: "code", label: "Code" },
                { key: "max_employees", label: "Employees", align: "right", render: (r) => (Number(r.max_employees) ? String(r.max_employees) : "Unlimited") },
                { key: "features", label: "Features", render: (r) => (r.features as string[]).join(", ") },
                { key: "monthly_price", label: "GHS / month", align: "right" }, { key: "trial_days", label: "Trial days", align: "right" },
                { key: "organizations", label: "Organizations", align: "right" }]}
              defaults={{ features: "[]", is_public: true }}
              fields={[{ name: "name", label: "Name", required: true, width: 6 }, { name: "code", label: "Code", required: true, width: 6 },
                { name: "max_employees", label: "Max active employees (0 = unlimited)", type: "number", width: 6 },
                { name: "monthly_price", label: "Price per month (GHS)", type: "number", width: 6 },
                { name: "features", label: "Features (JSON list)", type: "json", helper: "payroll, hospital, sms, biometric, geofence, ai_assistant" },
                { name: "trial_days", label: "Trial days", type: "number", width: 6 }, { name: "is_public", label: "Offered at sign-up", type: "checkbox", width: 6 }]} />
          </Card>
        )}
      </Box>
      <FormDialog open={creating} title="New organization" onClose={() => setCreating(false)} submitLabel="Create organization"
        intro="Creates the organization with Ghana defaults (roles, leave types, statutory tables, workflows) and emails a temporary password to its first administrator."
        initial={{ status: "trial" }}
        fields={[{ name: "name", label: "Organization name", required: true },
          { name: "code", label: "Address (subdomain)", required: true, helper: "Lowercase letters, numbers and hyphens, e.g. korlebu" },
          { name: "admin_username", label: "Administrator username", required: true, width: 6 },
          { name: "admin_email", label: "Administrator email", required: true, width: 6 },
          { name: "plan", label: "Plan", type: "select", options: (plans.data || []).map((p) => ({ value: p.id, label: p.name })), width: 6 },
          { name: "status", label: "Start as", type: "select", options: [{ value: "trial", label: "Trial" }, { value: "active", label: "Active" }], width: 6 }]}
        onSubmit={async (v) => { await api.post("/platform/organizations/", v); toast.ok("Organization created and administrator emailed."); inv("/platform/"); }} />
      {open && <OrgDialog org={open} plans={plans.data || []} onClose={() => setOpen(null)} />}
    </Box>
  );
}
