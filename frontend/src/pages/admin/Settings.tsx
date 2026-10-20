import { Button, Card, FormControlLabel, Grid2 as Grid, Stack, Switch, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ErrorAlert, Loading, useToast } from "../../components/Feedback";
import { FormFields, type FieldDef } from "../../components/FormDialog";
import { PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtDateTime } from "../../utils";

type Org = Record<string, unknown> & { settings: Record<string, unknown>; features: { code: string; label: string; enabled: boolean }[] };

const ORG_FIELDS: FieldDef[] = [
  { name: "name", label: "Display name", required: true, width: 6 }, { name: "legal_name", label: "Legal name (letterhead)", width: 6 },
  { name: "tin", label: "Employer TIN", width: 4 }, { name: "ssnit_employer_no", label: "SSNIT employer no.", width: 4 },
  { name: "currency", label: "Currency", width: 4 }, { name: "phone", label: "Phone", width: 4 }, { name: "email", label: "Email", width: 4 },
  { name: "website", label: "Website", width: 4 }, { name: "address", label: "Address", type: "textarea" },
];
const SETTING_FIELDS: FieldDef[] = [
  { name: "session_timeout_minutes", label: "Sign out after inactivity (minutes)", type: "number", width: 6 },
  { name: "retirement_age", label: "Compulsory retirement age", type: "number", width: 6 },
  { name: "leave_encashment", label: "Pay unused annual leave on final settlement", type: "checkbox", width: 6 },
  { name: "ess_direct_contact_updates", label: "Employees may update emergency contacts directly", type: "checkbox", width: 6 },
  { name: "celebration_notifications", label: "Birthday & work-anniversary greetings", type: "checkbox", width: 6 },
  { name: "loan_limits", label: "Loan limits (JSON)", type: "json", helper: '{"salary_advance": {"max_installments": 3, "max_salary_multiple": 1}, "staff_loan": {"max_installments": 24, "max_salary_multiple": 6}}' },
  { name: "gl_accounts", label: "GL accounts (JSON)", type: "json", helper: '{"salary_expense": "6000", "paye_payable": "2100", "ssnit_payable": "2110", "net_salaries_payable": "2200"}' },
];

export default function Settings() {
  const [tab, setTab] = useState(0);
  const org = useApi<Org>("/organization/");
  const { refresh } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const [vals, setVals] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const year = new Date().getFullYear();
  if (org.isLoading) return <Loading />;
  if (!org.data) return <ErrorAlert error={org.error} />;
  const v = vals || { ...org.data, ...org.data.settings,
    loan_limits: JSON.stringify(org.data.settings.loan_limits || {}), gl_accounts: JSON.stringify(org.data.settings.gl_accounts || {}),
    session_timeout_minutes: org.data.settings.session_timeout_minutes ?? 30, retirement_age: org.data.settings.retirement_age ?? 60,
    ess_direct_contact_updates: org.data.settings.ess_direct_contact_updates ?? true };
  const save = async () => {
    setErr(null);
    try {
      const settings: Record<string, unknown> = {};
      for (const f of SETTING_FIELDS) {
        let x = v[f.name];
        if (f.type === "json" && typeof x === "string") x = x.trim() ? JSON.parse(x) : {};
        if (f.type === "number") x = Number(x);
        settings[f.name] = x;
      }
      const body: Record<string, unknown> = { settings };
      ORG_FIELDS.forEach((f) => { body[f.name] = v[f.name]; });
      await api.patch("/organization/", body);
      toast.ok("Settings saved."); setVals(null); inv("/organization/"); refresh();
    } catch (e) { setErr(e); }
  };
  return (
    <>
      <PageHeader title="Organization settings" />
      <Tabs value={tab} onChange={(_, t) => setTab(t)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label="Organization & policies" /><Tab label="Modules" /><Tab label="Public holidays" /><Tab label="Numbering" /><Tab label="Custom fields" /><Tab label="Change history" />
      </Tabs>
      {tab === 0 && (
        <>
          <Section title="Organization profile"><FormFields fields={ORG_FIELDS} values={v} errors={{}} setValue={(k, x) => setVals({ ...v, [k]: x })} /></Section>
          <Section title="Policies"><FormFields fields={SETTING_FIELDS} values={v} errors={{}} setValue={(k, x) => setVals({ ...v, [k]: x })} /></Section>
          <ErrorAlert error={err} />
          <Button variant="contained" onClick={save}>Save settings</Button>
        </>
      )}
      {tab === 1 && (
        <Section title="Modules & integrations">
          <Grid container spacing={2}>
            {org.data.features.map((f) => (
              <Grid key={f.code} size={{ xs: 12, sm: 6 }}>
                <FormControlLabel control={<Switch checked={f.enabled} onChange={async (e) => {
                  await post("/organization/features/", { code: f.code, enabled: e.target.checked }); inv("/organization/"); refresh();
                }} />} label={<Stack><Typography fontWeight={600}>{f.label}</Typography>
                  <Typography variant="caption" color="text.secondary">{{ payroll: "Ghana payroll engine, payslips, bank files", hospital: "Clinical licences, competency matrix, credential checks on rosters",
                    sms: "SMS alerts via Hubtel/Arkesel (configure keys on the server)", biometric: "Sync ZKTeco terminals every 10 minutes", geofence: "Location check for web/mobile clock-in" }[f.code]}</Typography></Stack>} />
              </Grid>
            ))}
          </Grid>
        </Section>
      )}
      {tab === 2 && <Card><ResourcePage embedded title="Holiday" url="/admin/holidays/" params={{ year }} canDelete searchable={false}
        headerActions={<Button onClick={async () => { const r = await post<{ created: number }>("/admin/holidays/seed-ghana/", { year: year + 1 }); toast.ok(`${r.created} Ghana holidays added for ${year + 1}.`); inv("/admin/holidays/"); }}>
          Add Ghana holidays for {year + 1}</Button>}
        columns={[{ key: "date", label: "Date", render: (r) => fmtDate(r.date as string) }, { key: "name", label: "Holiday" },
          { key: "is_recurring", label: "Every year", render: (r) => (r.is_recurring ? "Yes" : "") }]}
        fields={[{ name: "name", label: "Name", required: true }, { name: "date", label: "Date", type: "date", required: true, width: 6 },
          { name: "is_recurring", label: "Same date every year", type: "checkbox", width: 6 }]}
        intro="Eid al-Fitr and Eid al-Adha dates are announced annually — add them here when gazetted." /></Card>}
      {tab === 3 && <Card><ResourcePage embedded title="Sequence" url="/admin/number-sequences/" searchable={false}
        columns={[{ key: "key", label: "Key" }, { key: "prefix", label: "Prefix" }, { key: "pattern", label: "Pattern" }, { key: "next_value", label: "Next" },
          { key: "reset_yearly", label: "Yearly reset", render: (r) => (r.reset_yearly ? "Yes" : "") }]}
        fields={[{ name: "key", label: "Key (e.g. staff_number)", required: true, width: 6 }, { name: "prefix", label: "Prefix", width: 6 },
          { name: "pattern", label: "Pattern", helper: "{prefix}, {seq:05d}, {year}, {yy}", width: 6 }, { name: "next_value", label: "Next value", type: "number", width: 6 },
          { name: "reset_yearly", label: "Reset each year", type: "checkbox" }]} defaults={{ pattern: "{prefix}{seq:05d}", next_value: 1 }} /></Card>}
      {tab === 4 && <Card><ResourcePage embedded title="Custom field" url="/admin/custom-fields/" canDelete searchable={false}
        columns={[{ key: "entity", label: "Entity" }, { key: "label", label: "Label" }, { key: "key", label: "Key" }, { key: "field_type", label: "Type" },
          { key: "required", label: "Required", render: (r) => (r.required ? "Yes" : "") }]}
        fields={[{ name: "label", label: "Label", required: true, width: 6 }, { name: "key", label: "Key", required: true, width: 6 },
          { name: "field_type", label: "Type", type: "select", width: 6, options: ["text", "number", "date", "bool", "choice"].map((x) => ({ value: x, label: x })) },
          { name: "choices", label: "Choices (JSON list)", type: "json", width: 6 }, { name: "required", label: "Required", type: "checkbox", width: 6 },
          { name: "is_sensitive", label: "Sensitive (personal data)", type: "checkbox", width: 6 }]} defaults={{ entity: "employee", field_type: "text", choices: "[]" }} /></Card>}
      {tab === 5 && <Card><ResourcePage embedded title="Change" url="/admin/config-changes/" searchable={false}
        columns={[{ key: "created_at", label: "When", render: (r) => fmtDateTime(r.created_at as string) }, { key: "area", label: "Area" }, { key: "object_repr", label: "Object" }]} /></Card>}
    </>
  );
}
