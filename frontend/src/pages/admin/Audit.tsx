import VerifiedUser from "@mui/icons-material/VerifiedUser";
import { Alert, Button, Card, Chip, MenuItem, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDateTime } from "../../utils";

const ACTIONS = ["create", "update", "delete", "view", "export", "download", "login", "login_failed", "logout", "workflow", "payroll", "permission", "config"];

export default function Audit() {
  const [tab, setTab] = useState(0);
  const [action, setAction] = useState("");
  const [verify, setVerify] = useState<{ intact: boolean; entries: number; first_invalid_entry: number | null } | null>(null);
  const review = useApi<Record<string, unknown>[]>(tab === 1 ? "/audit/logs/access-review/" : null);
  return (
    <>
      <PageHeader title="Audit trail" subtitle="Append-only and hash-chained: any alteration or deletion of past entries is detectable."
        actions={<Button startIcon={<VerifiedUser />} onClick={async () => setVerify((await api.get("/audit/logs/verify/")).data)}>Verify integrity</Button>} />
      {verify && <Alert severity={verify.intact ? "success" : "error"} sx={{ mb: 2 }} onClose={() => setVerify(null)}>
        {verify.intact ? `Audit chain intact — ${verify.entries} entries verified.` : `Tampering detected at entry #${verify.first_invalid_entry}. Escalate to your security officer.`}</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Activity log" /><Tab label="Sensitive access review" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Audit" url="/audit/logs/" params={{ action }}
          filters={<TextField select label="Action" value={action} onChange={(e) => setAction(e.target.value)} sx={{ minWidth: 160 }}>
            <MenuItem value="">All</MenuItem>{ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}</TextField>}
          columns={[{ key: "timestamp", label: "When", render: (r) => fmtDateTime(r.timestamp as string) }, { key: "actor_repr", label: "User" },
            { key: "action", label: "Action", render: (r) => <Chip variant="outlined" label={r.action as string} color={["delete", "login_failed", "permission"].includes(r.action as string) ? "warning" : "default"} /> },
            { key: "model", label: "Record type" }, { key: "object_repr", label: "Record" },
            { key: "changes", label: "Changes", render: (r) => <code style={{ fontSize: 11, wordBreak: "break-all" }}>{JSON.stringify(r.changes).slice(0, 220)}</code> },
            { key: "ip_address", label: "IP" }]} />}
        {tab === 1 && <DataTable dense loading={review.isLoading} rows={(review.data || []).map((r, i) => ({ ...r, id: i }))} columns={[
          { key: "user", label: "User" }, { key: "role", label: "Role" }, { key: "scope", label: "Scope" },
          { key: "sensitive_permissions", label: "Sensitive permissions", render: (r) => (r.sensitive_permissions as string[]).join(", ") },
          { key: "last_login", label: "Last login", render: (r) => fmtDateTime(r.last_login as string) },
          { key: "flag", label: "", render: (r) => r.flag ? <Chip color="error" label={r.flag as string} /> : null }]} />}
      </Card>
    </>
  );
}
