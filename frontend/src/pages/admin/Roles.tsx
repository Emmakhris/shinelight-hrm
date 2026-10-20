import Add from "@mui/icons-material/Add";
import Lock from "@mui/icons-material/Lock";
import { Box, Button, Card, Checkbox, FormControlLabel, Grid2 as Grid, List, ListItemButton, ListItemText, Stack, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate, useList } from "../../api/hooks";
import { ErrorAlert, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader, Section } from "../../components/PageHeader";
import { titleCase } from "../../utils";

interface Role { id: number; code: string; name: string; description: string; default_scope: string; is_system: boolean; requires_mfa: boolean; permissions: string[]; user_count: number }
interface Perm { code: string; name: string; module: string; is_sensitive: boolean }

export default function Roles() {
  const roles = useList<Role>("/admin/roles/");
  const perms = useApi<Perm[]>("/admin/permissions/");
  const [sel, setSel] = useState<number | null>(null);
  const [draft, setDraft] = useState<string[]>([]);
  const [mfa, setMfa] = useState(false);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const role = roles.items.find((r) => r.id === sel) || roles.items[0];
  useEffect(() => { if (role) { setDraft(role.permissions); setMfa(role.requires_mfa); } }, [role?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const modules = useMemo(() => {
    const m = new Map<string, Perm[]>();
    (perms.data || []).forEach((p) => { if (!m.has(p.module)) m.set(p.module, []); m.get(p.module)!.push(p); });
    return [...m.entries()];
  }, [perms.data]);
  const save = async () => {
    setErr(null);
    try { await api.patch(`/admin/roles/${role!.id}/`, { permissions: draft, requires_mfa: mfa }); toast.ok("Role updated (audited)."); inv("/admin/roles/"); }
    catch (e) { setErr(e); }
  };
  return (
    <>
      <PageHeader title="Roles & permissions" subtitle="Least privilege: grant each role only what it needs. Sensitive permissions are marked with a lock."
        actions={<Button variant="contained" startIcon={<Add />} onClick={() => setCreating(true)}>New role</Button>} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 3 }}>
          <Card><List dense>
            {roles.items.map((r) => (
              <ListItemButton key={r.id} selected={role?.id === r.id} onClick={() => setSel(r.id)}>
                <ListItemText primary={r.name} secondary={`${r.user_count} user(s) · default scope: ${r.default_scope}`} />
              </ListItemButton>
            ))}
          </List></Card>
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          {role && (
            <Section title={role.name} actions={<Button variant="contained" onClick={save}>Save changes</Button>}>
              <ErrorAlert error={err} />
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{role.description}</Typography>
              <FormControlLabel control={<Checkbox checked={mfa} onChange={(e) => setMfa(e.target.checked)} />} label="Require two-step verification (MFA) for users with this role" />
              <Grid container spacing={2} sx={{ mt: 1 }}>
                {modules.map(([mod, ps]) => (
                  <Grid key={mod} size={{ xs: 12, sm: 6, lg: 4 }}>
                    <Box sx={{ border: "1px solid #e3e8ef", borderRadius: 2, p: 1.5 }}>
                      <Typography fontWeight={650} sx={{ mb: 0.5 }}>{titleCase(mod)}</Typography>
                      {ps.map((p) => (
                        <Stack key={p.code} direction="row" alignItems="center">
                          <FormControlLabel sx={{ flex: 1 }} control={<Checkbox size="small" checked={draft.includes(p.code)}
                            onChange={(e) => setDraft(e.target.checked ? [...draft, p.code] : draft.filter((c) => c !== p.code))} />}
                            label={<Typography variant="body2">{p.name}</Typography>} />
                          {p.is_sensitive && <Lock sx={{ fontSize: 14, color: "warning.main" }} titleAccess="Sensitive" />}
                        </Stack>
                      ))}
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Section>
          )}
        </Grid>
      </Grid>
      <FormDialog open={creating} onClose={() => setCreating(false)} title="New role"
        fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
          { name: "default_scope", label: "Default scope", type: "select", options: ["own", "team", "department", "branch", "organization"].map((v) => ({ value: v, label: titleCase(v) })) },
          { name: "description", label: "Description", type: "textarea" }]}
        initial={{ default_scope: "own" }}
        onSubmit={async (d) => { await api.post("/admin/roles/", { ...(d as Record<string, unknown>), permissions: [] }); toast.ok("Role created."); inv("/admin/roles/"); }} />
    </>
  );
}
