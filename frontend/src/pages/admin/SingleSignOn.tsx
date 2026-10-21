import { Alert, Button, Card, Typography } from "@mui/material";
import { api } from "../../api/client";
import { useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

const callback = `${window.location.origin}/api/sso/callback/`;

export default function SingleSignOn() {
  const toast = useToast();
  const test = async (id: unknown) => {
    const { data } = await api.post(`/admin/sso-providers/${id}/test/`);
    if (data.ok) toast.ok(`Connected to ${data.issuer}.`);
    else toast.error(data.detail || "Could not reach the identity provider.");
  };
  return (
    <>
      <PageHeader title="Single sign-on" subtitle="Let staff sign in with their organization account (Microsoft 365 / Entra ID, Google Workspace, Okta or any OpenID Connect provider)." />
      <Alert severity="info" sx={{ mb: 2 }}>
        Register ShineLight HRM as a web application in your identity provider with the redirect URI
        <Typography component="code" sx={{ display: "block", fontFamily: "monospace", my: 0.5, wordBreak: "break-all" }}>{callback}</Typography>
        then enter its issuer URL, client ID and secret here. Staff are matched by work email to their existing
        account; turn on "Create logins" to give active employees without a login one automatically. Multi-factor
        authentication for SSO sign-ins is enforced by your identity provider.
      </Alert>
      <Card>
        <ResourcePage embedded title="Identity provider" url="/admin/sso-providers/" canDelete searchable={false}
          columns={[{ key: "name", label: "Name" }, { key: "email_domains", label: "Email domains" },
            { key: "allow_password_login", label: "Passwords", render: (r) => (r.allow_password_login ? "Allowed" : "SSO only") },
            { key: "linked_users", label: "Linked users", align: "right" },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          rowActions={(r) => <Button size="small" onClick={() => test(r.id)}>Test connection</Button>}
          defaults={{ scopes: "openid email profile", email_claim: "email", allow_password_login: true, is_active: true }}
          fields={[{ name: "name", label: "Button label (e.g. Microsoft 365)", required: true },
            { name: "issuer", label: "Issuer URL", required: true, helper: "Microsoft: https://login.microsoftonline.com/<tenant-id>/v2.0 · Google: https://accounts.google.com" },
            { name: "client_id", label: "Client (application) ID", required: true, width: 6 },
            { name: "client_secret", label: "Client secret (leave blank to keep)", width: 6 },
            { name: "email_domains", label: "Work email domains (comma separated)", required: true },
            { name: "email_claim", label: "Email claim", width: 6, helper: "Microsoft often needs preferred_username" },
            { name: "scopes", label: "Scopes", width: 6 },
            { name: "allow_password_login", label: "Allow password sign-in for these domains", type: "checkbox", width: 6 },
            { name: "auto_create_accounts", label: "Create logins for matching active employees", type: "checkbox", width: 6 },
            { name: "is_active", label: "Active", type: "checkbox" }]} />
      </Card>
      <Alert severity="warning" sx={{ mt: 2 }}>
        When password sign-in is switched off, users who can manage organization settings can still sign in with a password, so you are never locked out if the identity provider is down.
      </Alert>
    </>
  );
}
