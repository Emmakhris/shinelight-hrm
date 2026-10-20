import { Alert, Button, Card, Link, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useInvalidate, useList } from "../../api/hooks";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDateTime } from "../../utils";

export default function Integrations() {
  const [tab, setTab] = useState(0);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const events = useList<{ code: string; label: string }>("/integrations/webhooks/events/");
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Integrations & API" subtitle={<>REST API documentation: <Link href="/api/docs/" target="_blank" rel="noopener">/api/docs/</Link> · authenticate with <code>Authorization: Api-Key …</code></>} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="API keys" /><Tab label="Webhooks" /></Tabs>
      {newKey && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNewKey(null)}>
        Copy this key now — it will not be shown again:<Typography component="pre" sx={{ fontFamily: "monospace", mt: 1, wordBreak: "break-all", whiteSpace: "pre-wrap" }}>{newKey}</Typography></Alert>}
      <Card>
        {tab === 0 && <ResourcePage embedded title="API key" url="/integrations/api-keys/" canDelete canCreate={false} searchable={false}
          headerActions={<Button variant="contained" onClick={() => setCreating(true)}>New API key</Button>}
          columns={[{ key: "name", label: "Name" }, { key: "prefix", label: "Prefix" }, { key: "service_user_name", label: "Runs as" },
            { key: "last_used_at", label: "Last used", render: (r) => fmtDateTime(r.last_used_at as string) },
            { key: "expires_at", label: "Expires", render: (r) => fmtDateTime(r.expires_at as string) },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Name", required: true }, { name: "is_active", label: "Active", type: "checkbox" },
            { name: "allowed_ips", label: "Allowed IPs (JSON list)", type: "json" }]} />}
        {tab === 1 && <ResourcePage embedded title="Webhook" url="/integrations/webhooks/" canDelete searchable={false}
          intro="Each delivery is signed with HMAC-SHA256 in the X-ShineLight-Signature header. Failed deliveries are retried with back-off."
          columns={[{ key: "name", label: "Name" }, { key: "url", label: "URL" }, { key: "events", label: "Events", render: (r) => (r.events as string[]).join(", ") },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Name", required: true }, { name: "url", label: "Endpoint URL (https)", required: true },
            { name: "events", label: "Events (JSON list)", type: "json", required: true, helper: events.items.map((e) => e.code).join(", ") },
            { name: "is_active", label: "Active", type: "checkbox" }]} defaults={{ events: "[]", is_active: true }} />}
      </Card>
      <FormDialog open={creating} onClose={() => setCreating(false)} title="New API key" submitLabel="Generate key"
        intro="The key acts with the permissions of the chosen service user. Create a dedicated user with only the roles the integration needs."
        fields={[{ name: "name", label: "Name (e.g. Finance system)", required: true },
          { name: "service_user", label: "Service user", type: "ref", ref: "/admin/users/", refLabel: (u) => String(u.username), required: true },
          { name: "expires_at", label: "Expires at", type: "datetime" }, { name: "allowed_ips", label: "Allowed IPs (JSON list, optional)", type: "json" }]}
        initial={{ allowed_ips: "[]" }}
        onSubmit={async (d) => { const r = (await api.post("/integrations/api-keys/", d)).data; setNewKey(r.key); inv("/integrations/"); }} />
    </>
  );
}
