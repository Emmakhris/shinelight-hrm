import { Button, Card, Chip, Stack, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useInvalidate, useList } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDateTime } from "../../utils";

const SCOPES = [{ value: "own", label: "Own records" }, { value: "team", label: "Team (reports)" }, { value: "department", label: "Department" },
  { value: "branch", label: "Branch" }, { value: "organization", label: "Whole organization" }];

export default function Users() {
  const [tab, setTab] = useState(0);
  const [assigning, setAssigning] = useState<Record<string, unknown> | null>(null);
  const roles = useList<{ id: number; name: string }>("/admin/roles/");
  const toast = useToast();
  const inv = useInvalidate();
  const act = async (id: unknown, path: string) => {
    const r = (await api.post(`/admin/users/${id}/${path}/`)).data as { detail: string; temporary_password?: string };
    toast.ok(r.temporary_password ? `${r.detail} Temporary password: ${r.temporary_password}` : r.detail);
    inv("/admin/");
  };
  return (
    <>
      <PageHeader title="Users & access" subtitle="Individual accounts only — no shared logins. Role changes are audited; you cannot change your own roles." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Users" /><Tab label="Role assignments" /><Tab label="Login monitoring" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="User" url="/admin/users/" createLabel="Create user"
          intro="Staff accounts are best created from the employee record (Employees → Create user account) so the login is linked to their HR record."
          columns={[{ key: "username", label: "Username" }, { key: "name", label: "Name", render: (r) => `${r.first_name} ${r.last_name}` },
            { key: "email", label: "Email" },
            { key: "roles", label: "Roles", render: (r) => <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>{(r.roles as { id: number; name: string; scope: string }[]).map((x) =>
              <Chip key={x.id} label={`${x.name} · ${x.scope}`} onDelete={async () => { await api.delete(`/admin/role-assignments/${x.id}/`); inv("/admin/"); }} />)}</Stack> },
            { key: "mfa_enabled", label: "MFA", render: (r) => (r.mfa_enabled ? "On" : "Off") },
            { key: "is_active", label: "Status", render: (r) => r.is_locked ? <Chip color="error" label="Locked" /> : r.is_active ? "Active" : <Chip label="Disabled" /> },
            { key: "last_login", label: "Last login", render: (r) => fmtDateTime(r.last_login as string) }]}
          rowActions={(r) => <>
            <Button size="small" onClick={() => setAssigning(r)}>Add role</Button>
            {!!r.is_locked && <Button size="small" onClick={() => act(r.id, "unlock")}>Unlock</Button>}
            <Button size="small" onClick={() => act(r.id, "reset_password")}>Reset password</Button>
            {!!r.mfa_enabled && <Button size="small" onClick={() => act(r.id, "reset_mfa")}>Reset MFA</Button>}
            {!!r.is_active && <Button size="small" color="error" onClick={() => act(r.id, "deactivate")}>Disable</Button>}
          </>}
          canEdit={false}
          fields={[{ name: "username", label: "Username", required: true }, { name: "first_name", label: "First name", width: 6 }, { name: "last_name", label: "Last name", width: 6 },
            { name: "email", label: "Email (temporary password sent here)", type: "email", width: 6 }, { name: "phone", label: "Phone (for SMS codes)", width: 6 }]} />}
        {tab === 1 && <ResourcePage embedded title="Assignment" url="/admin/role-assignments/" canDelete canEdit={false} searchable={false}
          columns={[{ key: "user_name", label: "User" }, { key: "role_name", label: "Role" }, { key: "effective_scope", label: "Scope" },
            { key: "valid_from", label: "From" }, { key: "valid_to", label: "To" }]} />}
        {tab === 2 && <ResourcePage embedded title="Login attempts" url="/admin/login-attempts/" searchable={false}
          columns={[{ key: "timestamp", label: "Time", render: (r) => fmtDateTime(r.timestamp as string) }, { key: "username", label: "Username" },
            { key: "success", label: "Result", render: (r) => r.success ? <Chip color="success" variant="outlined" label="Success" /> : <Chip color="error" variant="outlined" label={String(r.reason)} /> },
            { key: "ip_address", label: "IP" }, { key: "user_agent", label: "Device", render: (r) => String(r.user_agent).slice(0, 60) }]} />}
      </Card>
      <FormDialog open={!!assigning} onClose={() => setAssigning(null)} title={`Grant role to ${assigning?.username}`} submitLabel="Grant"
        intro="Scope limits which employees' records the role applies to. Leave blank to use the role's default scope."
        fields={[{ name: "role", label: "Role", type: "select", required: true, options: roles.items.map((r) => ({ value: r.id, label: r.name })) },
          { name: "scope", label: "Scope", type: "select", options: SCOPES },
          { name: "department", label: "Department (department scope)", type: "ref", ref: "/org/departments/", hidden: (v) => v.scope !== "department", width: 6 },
          { name: "branch", label: "Branch (branch scope)", type: "ref", ref: "/org/branches/", hidden: (v) => v.scope !== "branch", width: 6 },
          { name: "valid_from", label: "Valid from", type: "date", width: 6 }, { name: "valid_to", label: "Valid to (e.g. acting role)", type: "date", width: 6 }]}
        onSubmit={async (d) => { await api.post("/admin/role-assignments/", { ...(d as Record<string, unknown>), user: assigning!.id }); toast.ok("Role granted."); inv("/admin/"); }} />
    </>
  );
}
